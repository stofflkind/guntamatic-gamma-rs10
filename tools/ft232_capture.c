#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <time.h>

#include <libftdi1/ftdi.h>

#define VID         0x0403
#define PID         0x6001
#define SERIAL      "YOUR_FTDI_SERIAL"

#define BAUD        9600
#define DEFAULT_DURATION 10.0
#define BUFFER_SIZE 4096

static double now_seconds(void)
{
    struct timespec ts;

    clock_gettime(CLOCK_MONOTONIC, &ts);

    return (double)ts.tv_sec +
           (double)ts.tv_nsec / 1000000000.0;
}

int main(int argc, char *argv[])
{
    if (argc < 2 || argc > 3) {
        fprintf(stderr, "Usage: %s OUTPUT [SECONDS]\n", argv[0]);
        return 1;
    }

    const char *output_filename = argv[1];
    double duration = DEFAULT_DURATION;

    if (argc == 3) {
        char *end = NULL;
        duration = strtod(argv[2], &end);

        if (end == argv[2] || *end != '\0' || duration <= 0.0) {
            fprintf(stderr, "Ungueltige Capture-Dauer: %s\n", argv[2]);
            return 1;
        }
    }

    struct ftdi_context *ftdi;
    unsigned char buf[BUFFER_SIZE];

    FILE *out = NULL;

    long long total_samples = 0;
    long long low_count = 0;
    long long high_count = 0;
    long long edges = 0;

    unsigned long counts[256] = {0};

    int previous_rx = -1;
    int rc;

    double start;
    double elapsed;

    const double nominal_sample_rate = BAUD * 32.0;

    printf("FT232R Raw Capture\n");
    printf("==================\n\n");

    /*
     * FTDI-Kontext anlegen
     */
    ftdi = ftdi_new();

    if (ftdi == NULL) {
        fprintf(stderr, "ftdi_new() fehlgeschlagen\n");
        return 1;
    }

    /*
     * Genau unseren FT232R anhand seiner Seriennummer öffnen.
     */
    rc = ftdi_usb_open_desc(
        ftdi,
        VID,
        PID,
        NULL,
        SERIAL
    );

    if (rc < 0) {
        fprintf(
            stderr,
            "FT232R öffnen fehlgeschlagen: %s\n",
            ftdi_get_error_string(ftdi)
        );

        ftdi_free(ftdi);
        return 1;
    }

    printf("FT232R geöffnet\n");

    /*
     * 0x00:
     *
     * D0..D7 sind Eingänge.
     *
     * Wir wollen ausschließlich passiv lauschen und
     * keines der FT232R-Signale aktiv treiben.
     */
    rc = ftdi_set_bitmode(
        ftdi,
        0x00,
        BITMODE_BITBANG
    );

    if (rc < 0) {
        fprintf(
            stderr,
            "Bit-Bang-Modus fehlgeschlagen: %s\n",
            ftdi_get_error_string(ftdi)
        );

        goto cleanup;
    }

    /*
     * libftdi berücksichtigt den Bit-Bang-Modus bei
     * der Baudrateneinstellung.
     */
    rc = ftdi_set_baudrate(
        ftdi,
        BAUD
    );

    if (rc < 0) {
        fprintf(
            stderr,
            "Baudrate fehlgeschlagen: %s\n",
            ftdi_get_error_string(ftdi)
        );

        goto cleanup;
    }

    /*
     * Eventuell noch vorhandene USB-Daten verwerfen.
     */
    rc = ftdi_usb_purge_buffers(ftdi);

    if (rc < 0) {
        fprintf(
            stderr,
            "USB-Puffer konnten nicht geleert werden: %s\n",
            ftdi_get_error_string(ftdi)
        );

        goto cleanup;
    }

    /*
     * Rohdaten-Datei.
     */
    out = fopen(
        output_filename,
        "wb"
    );

    if (out == NULL) {
        perror("ft232_capture.bin");
        goto cleanup;
    }

    printf("Bit-Bang Baudrate : %d\n", BAUD);
    printf(
        "Soll-Samplerate   : %.0f Samples/s\n",
        nominal_sample_rate
    );
    printf(
        "Sample-Abstand    : %.3f us\n",
        1000000.0 / nominal_sample_rate
    );
    printf(
        "Capture-Dauer     : %.1f s\n",
        duration
    );
    printf(
        "USB-Puffer        : %d Bytes\n",
        BUFFER_SIZE
    );

    printf("\nCapture läuft ...\n");
    fflush(stdout);

    start = now_seconds();

    while ((now_seconds() - start) < duration) {

        rc = ftdi_read_data(
            ftdi,
            buf,
            sizeof(buf)
        );

        if (rc < 0) {
            fprintf(
                stderr,
                "\nread_data fehlgeschlagen: %s\n",
                ftdi_get_error_string(ftdi)
            );

            goto cleanup;
        }

        if (rc == 0)
            continue;

        /*
         * Rohsamples unverändert speichern.
         */
        if (fwrite(buf, 1, rc, out) != (size_t)rc) {
            perror("Schreiben der Capture-Datei");
            goto cleanup;
        }

        /*
         * Samples analysieren.
         */
        for (int i = 0; i < rc; i++) {

            unsigned char sample = buf[i];

            counts[sample]++;

            /*
             * D1 = RXD
             */
            int rx = (sample >> 1) & 1;

            if (rx)
                high_count++;
            else
                low_count++;

            if (
                previous_rx != -1 &&
                rx != previous_rx
            ) {
                edges++;
            }

            previous_rx = rx;
        }

        total_samples += rc;
    }

    elapsed = now_seconds() - start;

    fclose(out);
    out = NULL;

    printf("\nCapture beendet.\n\n");

    printf(
        "Laufzeit             : %.3f s\n",
        elapsed
    );

    printf(
        "Samples empfangen    : %lld\n",
        total_samples
    );

    if (elapsed > 0.0) {

        double actual =
            (double)total_samples / elapsed;

        double expected =
            nominal_sample_rate * elapsed;

        printf(
            "Samples pro Sekunde  : %.0f\n",
            actual
        );

        printf(
            "Samples erwartet     : %.0f\n",
            expected
        );

        printf(
            "Verhältnis Ist/Soll  : %.1f %%\n",
            100.0 *
            (double)total_samples /
            expected
        );
    }

    printf("\nRXD / D1:\n");

    printf(
        "  LOW    : %lld\n",
        low_count
    );

    printf(
        "  HIGH   : %lld\n",
        high_count
    );

    printf(
        "  Flanken : %lld\n",
        edges
    );

    printf("\nHäufigste Pinzustände:\n");

    /*
     * Einfache Ausgabe aller tatsächlich
     * vorkommenden Pinzustände.
     */
    for (int i = 0; i < 256; i++) {

        if (counts[i] != 0) {

            printf(
                "  0x%02x : %lu",
                i,
                counts[i]
            );

            if (total_samples > 0) {

                printf(
                    "  (%6.2f %%)",
                    100.0 *
                    (double)counts[i] /
                    (double)total_samples
                );
            }

            printf("\n");
        }
    }

    printf(
        "\nRohdaten gespeichert: %s\n",
        output_filename
    );

cleanup:

    if (out != NULL)
        fclose(out);

    /*
     * Ganz wichtig:
     * FT232R wieder in den normalen UART-Modus setzen.
     */
    ftdi_set_bitmode(
        ftdi,
        0x00,
        BITMODE_RESET
    );

    ftdi_usb_close(ftdi);
    ftdi_free(ftdi);

    printf(
        "FT232R wieder auf normalen UART-Modus gesetzt.\n"
    );

    return 0;
}
