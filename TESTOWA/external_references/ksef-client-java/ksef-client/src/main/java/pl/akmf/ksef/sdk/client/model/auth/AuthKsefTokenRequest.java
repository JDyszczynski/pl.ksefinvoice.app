package pl.akmf.ksef.sdk.client.model.auth;


import java.util.List;

public class AuthKsefTokenRequest {
    private String challenge;
    private ContextIdentifier contextIdentifier;
    private String encryptedToken;
    private IpAddressPolicy ipAddressPolicy;

    public AuthKsefTokenRequest() {

    }

    public AuthKsefTokenRequest(String challenge, ContextIdentifier contextIdentifier, String encryptedToken, IpAddressPolicy ipAddressPolicy) {
        this.challenge = challenge;
        this.contextIdentifier = contextIdentifier;
        this.encryptedToken = encryptedToken;
        this.ipAddressPolicy = ipAddressPolicy;
    }

    public String getChallenge() {
        return challenge;
    }

    public void setChallenge(String challenge) {
        this.challenge = challenge;
    }

    public ContextIdentifier getContextIdentifier() {
        return contextIdentifier;
    }

    public void setContextIdentifier(ContextIdentifier contextIdentifier) {
        this.contextIdentifier = contextIdentifier;
    }

    public String getEncryptedToken() {
        return encryptedToken;
    }

    public void setEncryptedToken(String encryptedToken) {
        this.encryptedToken = encryptedToken;
    }

    public IpAddressPolicy getIpAddressPolicy() {
        return ipAddressPolicy;
    }

    public void setIpAddressPolicy(IpAddressPolicy ipAddressPolicy) {
        this.ipAddressPolicy = ipAddressPolicy;
    }

    public static class IpAddressPolicy {
        private IpChangePolicyEnum onClientIpChange;
        private AllowedIps allowedIps;

        public IpAddressPolicy(IpChangePolicyEnum onClientIpChange, AllowedIps allowedIps) {
            this.onClientIpChange = onClientIpChange;
            this.allowedIps = allowedIps;
        }

        public IpAddressPolicy() {

        }

        public IpChangePolicyEnum getOnClientIpChange() {
            return onClientIpChange;
        }

        public void setOnClientIpChange(IpChangePolicyEnum onClientIpChange) {
            this.onClientIpChange = onClientIpChange;
        }

        public AllowedIps getAllowedIps() {
            return allowedIps;
        }

        public void setAllowedIps(AllowedIps allowedIps) {
            this.allowedIps = allowedIps;
        }
    }

    public enum IpChangePolicyEnum {
        IGNORE("ignore"),
        REJECT("reject");
        private final String value;

        IpChangePolicyEnum(String v) {
            value = v;
        }

        public String value() {
            return value;
        }

        public static IpChangePolicyEnum fromValue(String v) {
            for (IpChangePolicyEnum c : IpChangePolicyEnum.values()) {
                if (c.value.equals(v)) {
                    return c;
                }
            }
            throw new IllegalArgumentException(v);
        }
    }

    public static class AllowedIps {
        private List<String> ipAddress;
        private List<String> ipRange;
        private List<String> ipMask;

        public AllowedIps(List<String> ipAddress, List<String> ipRange, List<String> ipMask) {
            this.ipAddress = ipAddress;
            this.ipRange = ipRange;
            this.ipMask = ipMask;
        }

        public AllowedIps() {

        }

        public List<String> getIpAddress() {
            return ipAddress;
        }

        public void setIpAddress(List<String> ipAddress) {
            this.ipAddress = ipAddress;
        }

        public List<String> getIpRange() {
            return ipRange;
        }

        public void setIpRange(List<String> ipRange) {
            this.ipRange = ipRange;
        }

        public List<String> getIpMask() {
            return ipMask;
        }

        public void setIpMask(List<String> ipMask) {
            this.ipMask = ipMask;
        }
    }
}
