package pl.akmf.ksef.sdk.client.model.permission.search;

public class SubunitPermissionsQueryRequest {
    private SubunitPermissionsSubunitIdentifier subunitIdentifier;

    public SubunitPermissionsQueryRequest() {
    }

    public SubunitPermissionsQueryRequest(SubunitPermissionsSubunitIdentifier subunitIdentifier) {
        this.subunitIdentifier = subunitIdentifier;
    }

    public SubunitPermissionsSubunitIdentifier getSubunitIdentifier() {
        return subunitIdentifier;
    }

    public void setSubunitIdentifier(SubunitPermissionsSubunitIdentifier subunitIdentifier) {
        this.subunitIdentifier = subunitIdentifier;
    }
}

