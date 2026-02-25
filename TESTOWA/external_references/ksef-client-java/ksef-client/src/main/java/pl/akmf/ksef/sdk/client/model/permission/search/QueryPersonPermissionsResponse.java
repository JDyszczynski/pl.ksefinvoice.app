package pl.akmf.ksef.sdk.client.model.permission.search;

import java.util.List;

public class QueryPersonPermissionsResponse {
    private List<PersonPermission> permissions;
    private Boolean hasMore;

    QueryPersonPermissionsResponse() {
    }

    public QueryPersonPermissionsResponse(List<PersonPermission> permissions, Boolean hasMore) {
        this.permissions = permissions;
        this.hasMore = hasMore;
    }

    public List<PersonPermission> getPermissions() {
        return permissions;
    }

    public void setPermissions(List<PersonPermission> permissions) {
        this.permissions = permissions;
    }

    public Boolean getHasMore() {
        return hasMore;
    }

    public void setHasMore(Boolean hasMore) {
        this.hasMore = hasMore;
    }
}

