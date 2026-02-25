package pl.akmf.ksef.sdk.client.model.qrcode;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonValue;

public enum ContextIdentifierType {
    NIP("Nip"),
    INTERNALID("InternalId"),
    NIPVATUE("NipVatUe");

    private final String value;

    ContextIdentifierType(String value) {
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
    public static ContextIdentifierType fromValue(String value) {
        for (ContextIdentifierType b : ContextIdentifierType.values()) {
            if (b.value.equalsIgnoreCase(value)) {
                return b;
            }
        }
        throw new IllegalArgumentException("Unexpected value '" + value + "'");
    }
}