package pl.akmf.ksef.sdk.api.builders.permission.entity;

import pl.akmf.ksef.sdk.client.model.permission.search.EntityAuthorizationPermissionsQueryRequest;
import pl.akmf.ksef.sdk.client.model.permission.search.EntityAuthorizationsAuthorizedEntityIdentifier;
import pl.akmf.ksef.sdk.client.model.permission.search.EntityAuthorizationsAuthorizingEntityIdentifier;
import pl.akmf.ksef.sdk.client.model.permission.search.InvoicePermissionType;
import pl.akmf.ksef.sdk.client.model.permission.search.QueryType;

import java.util.List;

public class EntityAuthorizationPermissionsQueryRequestBuilder {
    private EntityAuthorizationsAuthorizingEntityIdentifier authorizingIdentifier;
    private EntityAuthorizationsAuthorizedEntityIdentifier authorizedIdentifier;
    private QueryType queryType;
    private List<InvoicePermissionType> permissionTypes;

    public EntityAuthorizationPermissionsQueryRequestBuilder withAuthorizingIdentifier(EntityAuthorizationsAuthorizingEntityIdentifier authorizingIdentifier) {
        this.authorizingIdentifier = authorizingIdentifier;
        return this;
    }

    public EntityAuthorizationPermissionsQueryRequestBuilder withAuthorizedIdentifier(EntityAuthorizationsAuthorizedEntityIdentifier authorizedIdentifier) {
        this.authorizedIdentifier = authorizedIdentifier;
        return this;
    }

    public EntityAuthorizationPermissionsQueryRequestBuilder withQueryType(QueryType queryType) {
        this.queryType = queryType;
        return this;
    }

    public EntityAuthorizationPermissionsQueryRequestBuilder withPermissionTypes(List<InvoicePermissionType> permissionTypes) {
        this.permissionTypes = permissionTypes;
        return this;
    }

    public EntityAuthorizationPermissionsQueryRequest build() {
        return new EntityAuthorizationPermissionsQueryRequest(authorizingIdentifier, authorizedIdentifier, queryType, permissionTypes);
    }
}