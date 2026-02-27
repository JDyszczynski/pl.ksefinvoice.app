package pl.akmf.ksef.sdk.api.builders.tokens;

import pl.akmf.ksef.sdk.client.model.auth.KsefTokenRequest;
import pl.akmf.ksef.sdk.client.model.auth.TokenPermissionType;

import java.util.List;

public class KsefTokenRequestBuilder {
    private List<TokenPermissionType> permissions;
    private String description;

    public KsefTokenRequestBuilder withPermissions(List<TokenPermissionType> permissions) {
        this.permissions = permissions;
        return this;
    }

    public KsefTokenRequestBuilder withDescription(String description) {
        this.description = description;
        return this;
    }

    public KsefTokenRequest build() {
        return new KsefTokenRequest(permissions, description);
    }
}