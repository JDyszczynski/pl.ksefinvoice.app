package pl.akmf.ksef.sdk.client.model.permission;

import pl.akmf.ksef.sdk.client.model.StatusInfo;

public class PermissionStatusInfo {
    private StatusInfo status;

    public PermissionStatusInfo() {

    }

    public PermissionStatusInfo(StatusInfo status) {
        this.status = status;
    }

    public StatusInfo getStatus() {
        return status;
    }

    public void setStatus(StatusInfo status) {
        this.status = status;
    }
}
