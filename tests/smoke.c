/* SPDX-License-Identifier: BSD-2-Clause
 * Copyright (c) 2026, Anne Skydancer (neo-j2k)
 *
 * Package smoke test: links the shipped library through the staged headers, encodes a 64 x 64 RGB image
 * losslessly into memory, decodes it again with the memory API into interleaved 8-bit samples and compares
 * every byte. It also checks the engine string and that an executor can be lent and taken back.
 */
#include <neoj2k/neoj2k.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct { unsigned char *data; size_t size, cap; } sink_t;

static size_t sink_write(void *buffer, size_t bytes, void *user)
{
    sink_t *s = (sink_t *)user;
    if (s->size + bytes > s->cap) {
        size_t cap = s->cap ? s->cap : 4096;
        while (cap < s->size + bytes) cap *= 2;
        unsigned char *n = (unsigned char *)realloc(s->data, cap);
        if (!n) return 0;
        s->data = n; s->cap = cap;
    }
    memcpy(s->data + s->size, buffer, bytes);
    s->size += bytes;
    return bytes;
}

static void say(const char *msg, void *user) { (void)user; fputs(msg, stderr); }

static void run_serial(void *user, unsigned count, nj2k_job_fn job, void *ctx)
{
    (void)user;
    for (unsigned i = 0; i < count; ++i) job(ctx, i);
}

#define CHECK(c) do { if (!(c)) { fprintf(stderr, "smoke: FAILED %s (line %d)\n", #c, __LINE__); return 1; } } while (0)

int main(void)
{
    enum { W = 64, H = 64, C = 3 };
    unsigned char *pixels = (unsigned char *)malloc(W * H * C);
    CHECK(pixels);
    for (int y = 0; y < H; ++y)
        for (int x = 0; x < W; ++x)
            for (int c = 0; c < C; ++c)
                pixels[(y * W + x) * C + c] = (unsigned char)((x * 17 + y * 11 + c * 47) % 256);

    printf("engine: %s, version %s\n", nj2k_engine_string(), nj2k_version());
    CHECK(strncmp(nj2k_engine_string(), "neo-j2k", 7) == 0);
    CHECK(strcmp(nj2k_version(), EXPECT_VERSION) == 0); /* the library reports the package version (VERSION.txt) */
    CHECK(nj2k_cpu_supported());

    /* encode, lossless, RLCP, as the viewer's reversible upload */
    nj2k_cparameters_t params;
    nj2k_set_default_encoder_parameters(&params);
    params.cod_format = NJ2K_CODEC_J2K;
    params.prog_order = NJ2K_RLCP;
    params.irreversible = 0;
    params.tcp_numlayers = 1;
    params.tcp_rates[0] = 0.0f;
    params.tcp_mct = 1;
    nj2k_image_cmptparm_t cp[C];
    memset(cp, 0, sizeof cp);
    for (int c = 0; c < C; ++c) { cp[c].prec = 8; cp[c].dx = 1; cp[c].dy = 1; cp[c].w = W; cp[c].h = H; }
    nj2k_image_t *image = nj2k_image_create(C, cp, NJ2K_CLRSPC_SRGB);
    CHECK(image);
    image->x1 = W; image->y1 = H;
    for (int i = 0; i < W * H; ++i)
        for (int c = 0; c < C; ++c) image->comps[c].data[i] = pixels[i * C + c];

    nj2k_codec_t *enc = nj2k_create_compress(NJ2K_CODEC_J2K);
    CHECK(enc);
    nj2k_set_error_handler(enc, say, NULL);
    nj2k_set_warning_handler(enc, say, NULL);
    CHECK(nj2k_setup_encoder(enc, &params, image));
    sink_t sink = { 0, 0, 0 };
    nj2k_stream_t *stream = nj2k_stream_create(65536, 0);
    CHECK(stream);
    nj2k_stream_set_user_data(stream, &sink, NULL);
    nj2k_stream_set_write_function(stream, sink_write);
    CHECK(nj2k_start_compress(enc, image, stream));
    CHECK(nj2k_encode(enc, stream));
    CHECK(nj2k_end_compress(enc, stream));
    nj2k_stream_destroy(stream);
    nj2k_destroy_codec(enc);
    nj2k_image_destroy(image);
    CHECK(sink.size > 16);

    /* decode through the memory API, with an executor lent and taken back */
    nj2k_codec_t *dec = nj2k_create_decompress(NJ2K_CODEC_J2K);
    CHECK(dec);
    nj2k_dparameters_t dp;
    nj2k_set_default_decoder_parameters(&dp);
    CHECK(nj2k_setup_decoder(dec, &dp));
    nj2k_executor_t ex;
    memset(&ex, 0, sizeof ex);
    ex.struct_size = sizeof ex;
    ex.concurrency = 4;
    ex.parallel_for = run_serial;
    CHECK(nj2k_decoder_set_executor(dec, &ex));

    nj2k_image_t described;
    memset(&described, 0, sizeof described);
    CHECK(nj2k_read_header_memory(dec, sink.data, sink.size, &described));
    CHECK(described.numcomps == C && described.comps[0].w == W && described.comps[0].h == H);

    unsigned char *out = (unsigned char *)calloc(W * H * C, 1);
    CHECK(out);
    nj2k_plane_t planes[C];
    for (int c = 0; c < C; ++c) {
        planes[c].data = out + c;
        planes[c].row_stride = W * C;
        planes[c].sample_stride = C;
        planes[c].component = (unsigned)c;
    }
    nj2k_output_t output;
    memset(&output, 0, sizeof output);
    output.struct_size = sizeof output;
    output.sample_type = NJ2K_SAMPLE_U8;
    output.numplanes = C;
    output.planes = planes;
    CHECK(nj2k_decode_memory(dec, sink.data, sink.size, &output));
    CHECK(nj2k_get_status(dec) == NJ2K_OK);
    CHECK(memcmp(out, pixels, W * H * C) == 0);
    CHECK(nj2k_decoder_set_executor(dec, NULL));
    nj2k_destroy_codec(dec);

    free(out); free(sink.data); free(pixels);
    printf("smoke: PASS (%zu bytes encoded, %d x %d x %d lossless round trip exact)\n", sink.size, W, H, C);
    return 0;
}
