package pl.akmf.ksef.sdk.api.builders.permission.euentity;

import pl.akmf.ksef.sdk.client.model.permission.search.EuEntityPermissionsQueryPermissionType;
import pl.akmf.ksef.sdk.client.model.permission.search.EuEntityPermissionsQueryRequest;

import java.util.List;

public class EuEntityPermissionsQueryRequestBuilder {
    private String vatUeIdentifier;
    private String authorizedFingerprintIdentifier;
    private List<EuEntityPermissionsQueryPermissionType> permissionTypes;

    public EuEntityPermissionsQueryRequestBuilder withVatUeIdentifier(String vatUeIdentifier) {
        this.vatUeIdentifier = vatUeIdentifier;
        return this;
    }

    public EuEntityPermissionsQueryRequestBuilder withAuthorizedFingerprintIdentifier(String authorizedFingerprintIdentifier) {
        this.authorizedFingerprintIdentifier = authorizedFingerprintIdentifier;
        return this;
    }

    public EuEntityPermissionsQueryRequestBuilder withPermissionTypes(List<EuEntityPermissionsQueryPermissionType> permissionTypes) {
        this.permissionTypes = permissionTypes;
        return this;
    }

    public EuEntityPermissionsQueryRequest build() {
        return new EuEntityPermissionsQueryRequest(vatUeIdentifier, authorizedFingerprintIdentifier, permissionTypes);
    }
}