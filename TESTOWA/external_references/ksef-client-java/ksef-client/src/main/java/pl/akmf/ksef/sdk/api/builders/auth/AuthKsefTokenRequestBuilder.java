package pl.akmf.ksef.sdk.api.builders.auth;

import pl.akmf.ksef.sdk.client.model.auth.AuthKsefTokenRequest;
import pl.akmf.ksef.sdk.client.model.auth.ContextIdentifier;

public class AuthKsefTokenRequestBuilder {
    private String challenge;
    private ContextIdentifier contextIdentifier;
    private String encryptedToken;
    private AuthKsefTokenRequest.IpAddressPolicy ipAddressPolicy;

    public AuthKsefTokenRequestBuilder withChallenge(final String challenge) {
        this.challenge = challenge;
        return this;
    }

    public AuthKsefTokenRequestBuilder withContextIdentifier(final ContextIdentifier contextIdentifier) {
        this.contextIdentifier = contextIdentifier;
        return this;
    }

    public AuthKsefTokenRequestBuilder withEncryptedToken(final String encryptedToken) {
        this.encryptedToken = encryptedToken;
        return this;
    }

    public AuthKsefTokenRequestBuilder withIpAddressPolicy(final AuthKsefTokenRequest.IpAddressPolicy ipAddressPolicy) {
        this.ipAddressPolicy = ipAddressPolicy;
        return this;
    }

    public AuthKsefTokenRequest build() {
        return new AuthKsefTokenRequest(challenge, contextIdentifier, encryptedToken, ipAddressPolicy);
    }
}
