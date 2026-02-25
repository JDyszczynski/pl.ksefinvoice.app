package pl.akmf.ksef.sdk.client.model.permission.search;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonValue;

public enum EntityAuthorizationScope {

    SELF_INVOICING("SelfInvoicing"),
    TAX_REPRESENTATIVE("TaxRepresentative"),
    RR_INVOICING("RRInvoicing");

    private final String value;

    EntityAuthorizationScope(String value) {
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
    public static EntityAuthorizationScope fromValue(String value) {
        for (EntityAuthorizationScope b : EntityAuthorizationScope.values()) {
            if (b.value.equals(value)) {
                return b;
            }
        }
        throw new IllegalArgumentException("Unexpected value '" + value + "'");
    }
}

