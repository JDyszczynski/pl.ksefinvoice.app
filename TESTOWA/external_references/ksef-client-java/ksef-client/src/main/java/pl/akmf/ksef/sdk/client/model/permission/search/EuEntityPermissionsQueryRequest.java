package pl.akmf.ksef.sdk.client.model.permission.search;

import java.util.List;

public class EuEntityPermissionsQueryRequest {
    private String vatUeIdentifier;
    private String authorizedFingerprintIdentifier;
    private List<EuEntityPermissionsQueryPermissionType> permissionTypes;

    public EuEntityPermissionsQueryRequest() {
    }

    public EuEntityPermissionsQueryRequest(String vatUeIdentifier, String authorizedFingerprintIdentifier, List<EuEntityPermissionsQueryPermissionType> permissionTypes) {
        this.vatUeIdentifier = vatUeIdentifier;
        this.authorizedFingerprintIdentifier = authorizedFingerprintIdentifier;
        this.permissionTypes = permissionTypes;
    }

    public String getVatUeIdentifier() {
        return vatUeIdentifier;
    }

    public void setVatUeIdentifier(String vatUeIdentifier) {
        this.vatUeIdentifier = vatUeIdentifier;
    }

    public String getAuthorizedFingerprintIdentifier() {
        return authorizedFingerprintIdentifier;
    }

    public void setAuthorizedFingerprintIdentifier(String authorizedFingerprintIdentifier) {
        this.authorizedFingerprintIdentifier = authorizedFingerprintIdentifier;
    }

    public List<EuEntityPermissionsQueryPermissionType> getPermissionTypes() {
        return permissionTypes;
    }

    public void setPermissionTypes(List<EuEntityPermissionsQueryPermissionType> permissionTypes) {
        this.permissionTypes = permissionTypes;
    }
}