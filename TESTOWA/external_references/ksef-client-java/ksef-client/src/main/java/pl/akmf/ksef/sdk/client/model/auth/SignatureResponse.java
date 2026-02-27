package pl.akmf.ksef.sdk.client.model.auth;

public class SignatureResponse {
    private String referenceNumber;
    private TokenInfo authenticationToken;

    public SignatureResponse() {

    }

    public SignatureResponse(String referenceNumber, TokenInfo authenticationToken) {
        this.referenceNumber = referenceNumber;
        this.authenticationToken = authenticationToken;
    }

    public String getReferenceNumber() {
        return referenceNumber;
    }

    public void setReferenceNumber(String referenceNumber) {
        this.referenceNumber = referenceNumber;
    }

    public TokenInfo getAuthenticationToken() {
        return authenticationToken;
    }

    public void setAuthenticationToken(TokenInfo authenticationToken) {
        this.authenticationToken = authenticationToken;
    }
}

