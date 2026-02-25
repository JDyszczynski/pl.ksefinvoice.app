package pl.akmf.ksef.sdk.client.model.permission.search;

import java.util.List;


public class QueryEuEntityPermissionsResponse {
    private List<EuEntityPermission> permissions;
    private Boolean hasMore;

    QueryEuEntityPermissionsResponse() {
    }

    public QueryEuEntityPermissionsResponse(List<EuEntityPermission> permissions, Boolean hasMore) {
        this.permissions = permissions;
        this.hasMore = hasMore;
    }

    public List<EuEntityPermission> getPermissions() {
        return permissions;
    }

    public void setPermissions(List<EuEntityPermission> permissions) {
        this.permissions = permissions;
    }

    public Boolean getHasMore() {
        return hasMore;
    }

    public void setHasMore(Boolean hasMore) {
        this.hasMore = hasMore;
    }
}

