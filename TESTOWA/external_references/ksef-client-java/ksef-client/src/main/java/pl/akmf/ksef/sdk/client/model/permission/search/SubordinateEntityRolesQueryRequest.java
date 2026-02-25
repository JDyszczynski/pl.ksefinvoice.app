package pl.akmf.ksef.sdk.client.model.permission.search;

public class SubordinateEntityRolesQueryRequest {
    private EntityPermissionsSubordinateEntityIdentifier subordinateEntityIdentifier;

    public SubordinateEntityRolesQueryRequest() {
    }

    public SubordinateEntityRolesQueryRequest(EntityPermissionsSubordinateEntityIdentifier subordinateEntityIdentifier) {
        this.subordinateEntityIdentifier = subordinateEntityIdentifier;
    }

    public EntityPermissionsSubordinateEntityIdentifier getSubordinateEntityIdentifier() {
        return subordinateEntityIdentifier;
    }

    public void setSubordinateEntityIdentifier(EntityPermissionsSubordinateEntityIdentifier subordinateEntityIdentifier) {
        this.subordinateEntityIdentifier = subordinateEntityIdentifier;
    }
}

