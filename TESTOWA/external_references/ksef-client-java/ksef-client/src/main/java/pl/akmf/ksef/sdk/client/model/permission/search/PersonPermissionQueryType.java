package pl.akmf.ksef.sdk.client.model.permission.search;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonValue;

public enum PersonPermissionQueryType {
    PERMISSION_IN_CURRENT_CONTEXT("PermissionsInCurrentContext"),
    PERMISSION_GRANTED_IN_CURRENT_CONTEXT("PermissionsGrantedInCurrentContext");

    private final String value;

    PersonPermissionQueryType(String value) {
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
    public static PersonPermissionQueryType fromValue(String value) {
        for (PersonPermissionQueryType b : PersonPermissionQueryType.values()) {
            if (b.value.equals(value)) {
                return b;
            }
        }
        throw new IllegalArgumentException("Unexpected value '" + value + "'");
    }
}
