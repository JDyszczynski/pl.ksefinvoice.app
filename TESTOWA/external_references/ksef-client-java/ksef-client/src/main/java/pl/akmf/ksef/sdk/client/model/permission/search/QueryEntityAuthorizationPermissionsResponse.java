package pl.akmf.ksef.sdk.client.model.permission.search;

import java.util.List;

public class QueryEntityAuthorizationPermissionsResponse {
    private List<EntityAuthorizationGrant> authorizationGrants;
    private Boolean hasMore;

    QueryEntityAuthorizationPermissionsResponse() {
    }

    public QueryEntityAuthorizationPermissionsResponse(List<EntityAuthorizationGrant> authorizationGrants, Boolean hasMore) {
        this.authorizationGrants = authorizationGrants;
        this.hasMore = hasMore;
    }

    public List<EntityAuthorizationGrant> getAuthorizationGrants() {
        return authorizationGrants;
    }

    public void setAuthorizationGrants(List<EntityAuthorizationGrant> authorizationGrants) {
        this.authorizationGrants = authorizationGrants;
    }

    public Boolean getHasMore() {
        return hasMore;
    }

    public void setHasMore(Boolean hasMore) {
        this.hasMore = hasMore;
    }
}
