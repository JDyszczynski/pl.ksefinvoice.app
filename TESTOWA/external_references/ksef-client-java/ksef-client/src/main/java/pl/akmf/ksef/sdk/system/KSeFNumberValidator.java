package pl.akmf.ksef.sdk.system;

import java.nio.charset.StandardCharsets;

public class KSeFNumberValidator {
    private static final byte POLYNOMIAL = 0x07;
    private static final byte INIT_VALUE = 0x00;
    private static final int EXPECTED_LENGTH = 35;
    private static final int DATA_LENGTH = 32;
    private static final int CHECKSUM_LENGTH = 2;

    public KSeFNumberValidator(){

    }

    public static ValidationResult isValid(String ksefNumber) {
        if (ksefNumber == null || ksefNumber.trim().isEmpty()) {
            return new ValidationResult(false, "Numer KSeF jest pusty.");
        }

        if (ksefNumber.length() != EXPECTED_LENGTH) {
            String errorMessage = String.format("Numer KSeF ma nieprawidłową długość: %d. Oczekiwana długość to %d.",
                    ksefNumber.length(), EXPECTED_LENGTH);
            return new ValidationResult(false, errorMessage);
        }

        String data = ksefNumber.substring(0, DATA_LENGTH);
        String checksum = ksefNumber.substring(ksefNumber.length() - CHECKSUM_LENGTH);
        String calculated = computeChecksum(data.getBytes(StandardCharsets.UTF_8));

        boolean isValid = calculated.equals(checksum);
        return new ValidationResult(isValid, isValid ? "" : "Nieprawidłowa suma kontrolna.");
    }

    private static String computeChecksum(byte[] data) {
        byte crc = INIT_VALUE;

        for (byte b : data) {
            crc ^= b;
            for (int i = 0; i < 8; i++) {
                crc = (crc & 0x80) != 0
                        ? (byte) ((crc << 1) ^ POLYNOMIAL)
                        : (byte) (crc << 1);
            }
        }

        return String.format("%02X", crc); // always 2-char hex
    }

    public static class ValidationResult {
        private final boolean isValid;
        private final String errorMessage;

        public ValidationResult(boolean isValid, String errorMessage) {
            this.isValid = isValid;
            this.errorMessage = errorMessage;
        }

        public boolean isValid() {
            return isValid;
        }

        public String getErrorMessage() {
            return errorMessage;
        }
    }
}