package pl.akmf.ksef.sdk.api.builders.permission.subunit;

import pl.akmf.ksef.sdk.client.model.permission.search.SubunitPermissionsQueryRequest;
import pl.akmf.ksef.sdk.client.model.permission.search.SubunitPermissionsSubunitIdentifier;

public class SubunitPermissionsQueryRequestBuilder {
    private SubunitPermissionsSubunitIdentifier subunitIdentifier;

    public SubunitPermissionsQueryRequestBuilder withSubunitIdentifier(SubunitPermissionsSubunitIdentifier subunitIdentifier) {
        this.subunitIdentifier = subunitIdentifier;
        return this;
    }

    public SubunitPermissionsQueryRequest build() {
        return new SubunitPermissionsQueryRequest(subunitIdentifier);
    }
}