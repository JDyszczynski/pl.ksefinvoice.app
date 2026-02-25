package pl.akmf.ksef.sdk.client.model.auth;

public class AuthOperationStatusResponse {
    private TokenInfo accessToken;
    private TokenInfo refreshToken;

    public AuthOperationStatusResponse() {
    }

    public AuthOperationStatusResponse(TokenInfo accessToken, TokenInfo refreshToken) {
        this.accessToken = accessToken;
        this.refreshToken = refreshToken;
    }

    public TokenInfo getAccessToken() {
        return accessToken;
    }

    public void setAccessToken(TokenInfo accessToken) {
        this.accessToken = accessToken;
    }

    public TokenInfo getRefreshToken() {
        return refreshToken;
    }

    public void setRefreshToken(TokenInfo refreshToken) {
        this.refreshToken = refreshToken;
    }
}

