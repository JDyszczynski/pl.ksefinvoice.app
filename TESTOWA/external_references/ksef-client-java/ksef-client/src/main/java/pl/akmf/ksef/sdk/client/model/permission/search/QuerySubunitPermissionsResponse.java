package pl.akmf.ksef.sdk.client.model.permission.search;

import java.util.List;

public class QuerySubunitPermissionsResponse {
    private List<SubunitPermission> permissions;
    private Boolean hasMore;

    QuerySubunitPermissionsResponse() {
    }

    public QuerySubunitPermissionsResponse(List<SubunitPermission> permissions, Boolean hasMore) {
        this.permissions = permissions;
        this.hasMore = hasMore;
    }

    public List<SubunitPermission> getPermissions() {
        return permissions;
    }

    public void setPermissions(List<SubunitPermission> permissions) {
        this.permissions = permissions;
    }

    public Boolean getHasMore() {
        return hasMore;
    }

    public void setHasMore(Boolean hasMore) {
        this.hasMore = hasMore;
    }
}

