package pl.akmf.ksef.sdk.client.model.permission.search;


import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonValue;


public enum PermissionState {
  
  ACTIVE("Active"),
  
  INACTIVE("Inactive");

  private final String value;

  PermissionState(String value) {
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
  public static PermissionState fromValue(String value) {
    for (PermissionState b : PermissionState.values()) {
      if (b.value.equals(value)) {
        return b;
      }
    }
    throw new IllegalArgumentException("Unexpected value '" + value + "'");
  }
}

