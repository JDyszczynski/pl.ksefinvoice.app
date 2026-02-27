package pl.akmf.ksef.sdk.client.model.auth;

public class AuthenticationTokenRefreshResponse {
    private TokenInfo accessToken;

    public AuthenticationTokenRefreshResponse() {
    }

    public AuthenticationTokenRefreshResponse(TokenInfo accessToken) {
        this.accessToken = accessToken;
    }

    public TokenInfo getAccessToken() {
        return accessToken;
    }

    public void setAccessToken(TokenInfo accessToken) {
        this.accessToken = accessToken;
    }
}

