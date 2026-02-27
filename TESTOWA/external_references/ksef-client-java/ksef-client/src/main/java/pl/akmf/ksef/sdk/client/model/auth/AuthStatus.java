package pl.akmf.ksef.sdk.client.model.auth;

import pl.akmf.ksef.sdk.client.model.StatusInfo;
import pl.akmf.ksef.sdk.client.model.session.AuthenticationMethod;

import java.time.OffsetDateTime;

public class AuthStatus {
    private OffsetDateTime startDate;

    private AuthenticationMethod authenticationMethod;

    private StatusInfo status;

    private Boolean isTokenRedeemed;

    private OffsetDateTime lastTokenRefreshDate;

    private OffsetDateTime refreshTokenValidUntil;

    public AuthStatus() {
    }

    public OffsetDateTime getStartDate() {
        return startDate;
    }

    public void setStartDate(OffsetDateTime startDate) {
        this.startDate = startDate;
    }

    public AuthenticationMethod getAuthenticationMethod() {
        return authenticationMethod;
    }

    public void setAuthenticationMethod(AuthenticationMethod authenticationMethod) {
        this.authenticationMethod = authenticationMethod;
    }

    public StatusInfo getStatus() {
        return status;
    }

    public void setStatus(StatusInfo status) {
        this.status = status;
    }

    public Boolean getIsTokenRedeemed() {
        return isTokenRedeemed;
    }

    public void setIsTokenRedeemed(Boolean tokenRedeemed) {
        isTokenRedeemed = tokenRedeemed;
    }

    public OffsetDateTime getLastTokenRefreshDate() {
        return lastTokenRefreshDate;
    }

    public void setLastTokenRefreshDate(OffsetDateTime lastTokenRefreshDate) {
        this.lastTokenRefreshDate = lastTokenRefreshDate;
    }

    public OffsetDateTime getRefreshTokenValidUntil() {
        return refreshTokenValidUntil;
    }

    public void setRefreshTokenValidUntil(OffsetDateTime refreshTokenValidUntil) {
        this.refreshTokenValidUntil = refreshTokenValidUntil;
    }
}

