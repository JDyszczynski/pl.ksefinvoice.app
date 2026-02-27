package pl.akmf.ksef.sdk.client.model.auth;

public class GenerateTokenResponse {
    private String referenceNumber;
    private String token;

    public GenerateTokenResponse() {
    }

    public String getReferenceNumber() {
        return referenceNumber;
    }

    public void setReferenceNumber(String referenceNumber) {
        this.referenceNumber = referenceNumber;
    }

    public String getToken() {
        return token;
    }

    public void setToken(String token) {
        this.token = token;
    }
}
