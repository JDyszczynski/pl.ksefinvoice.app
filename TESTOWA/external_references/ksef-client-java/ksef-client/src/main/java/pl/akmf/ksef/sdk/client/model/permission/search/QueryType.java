package pl.akmf.ksef.sdk.client.model.permission.search;


import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonValue;

public enum QueryType {

    GRANTED("Granted"),

    RECEIVED("Received");

    private final String value;

    QueryType(String value) {
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
    public static QueryType fromValue(String value) {
        for (QueryType b : QueryType.values()) {
            if (b.value.equals(value)) {
                return b;
            }
        }
        throw new IllegalArgumentException("Unexpected value '" + value + "'");
    }
}

