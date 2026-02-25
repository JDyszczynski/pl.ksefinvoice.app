package pl.akmf.ksef.sdk.client.model.permission.entity;

public class EntityPermission {
  private EntityPermissionType type;
  private Boolean canDelegate;

  public EntityPermission() {
  }

  public EntityPermission(EntityPermissionType type, Boolean canDelegate) {
    this.type = type;
    this.canDelegate = canDelegate;
  }

  public EntityPermissionType getType() {
    return type;
  }

  public void setType(EntityPermissionType type) {
    this.type = type;
  }

  public Boolean getCanDelegate() {
    return canDelegate;
  }

  public void setCanDelegate(Boolean canDelegate) {
    this.canDelegate = canDelegate;
  }
}

