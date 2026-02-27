package pl.akmf.ksef.sdk.client.model.certificate;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonValue;

public enum CertificateListItemStatus {

    ACTIVE("Active"),

    BLOCKED("Blocked"),

    REVOKED("Revoked"),

    EXPIRED("Expired");

    private final String value;

    CertificateListItemStatus(String value) {
        this.value = value;
    }

    @JsonValue
    public String getValue() {
        return value;
    }

    @Override
    public String toString() {
        return String.valueOf(value);
    }

    @JsonCreator
    public static CertificateListItemStatus fromValue(String value) {
        for (CertificateListItemStatus b : CertificateListItemStatus.values()) {
            if (b.value.equalsIgnoreCase(value)) {
                return b;
            }
        }
        throw new IllegalArgumentException("Unexpected value '" + value + "'");
    }
}

