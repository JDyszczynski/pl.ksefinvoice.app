package pl.akmf.ksef.sdk.client.model.permission.search;

import java.util.List;

public class QueryEntityRolesResponse {
    private List<EntityRole> roles;
    private Boolean hasMore;

    QueryEntityRolesResponse() {
    }

    public QueryEntityRolesResponse(List<EntityRole> roles, Boolean hasMore) {
        this.roles = roles;
        this.hasMore = hasMore;
    }

    public List<EntityRole> getRoles() {
        return roles;
    }

    public void setRoles(List<EntityRole> roles) {
        this.roles = roles;
    }

    public Boolean getHasMore() {
        return hasMore;
    }

    public void setHasMore(Boolean hasMore) {
        this.hasMore = hasMore;
    }
}

