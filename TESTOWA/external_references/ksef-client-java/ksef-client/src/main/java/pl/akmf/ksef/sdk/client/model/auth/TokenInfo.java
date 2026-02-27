package pl.akmf.ksef.sdk.client.model.auth;

import java.time.OffsetDateTime;

public class TokenInfo {
    private String token;
    private OffsetDateTime validUntil;

    public TokenInfo() {
    }

    public TokenInfo(String token, OffsetDateTime validUntil) {
        this.token = token;
        this.validUntil = validUntil;
    }

    public String getToken() {
        return token;
    }

    public void setToken(String token) {
        this.token = token;
    }

    public OffsetDateTime getValidUntil() {
        return validUntil;
    }

    public void setValidUntil(OffsetDateTime validUntil) {
        this.validUntil = validUntil;
    }
}

