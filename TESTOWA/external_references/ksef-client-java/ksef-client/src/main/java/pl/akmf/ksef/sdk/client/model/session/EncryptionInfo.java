package pl.akmf.ksef.sdk.client.model.session;

public class EncryptionInfo {
    private String encryptedSymmetricKey;
    private String initializationVector;

    public EncryptionInfo() {
    }

    public EncryptionInfo(String encryptedSymmetricKey, String initializationVector) {
        this.encryptedSymmetricKey = encryptedSymmetricKey;
        this.initializationVector = initializationVector;
    }

    public String getEncryptedSymmetricKey() {
        return encryptedSymmetricKey;
    }

    public void setEncryptedSymmetricKey(String encryptedSymmetricKey) {
        this.encryptedSymmetricKey = encryptedSymmetricKey;
    }

    public String getInitializationVector() {
        return initializationVector;
    }

    public void setInitializationVector(String initializationVector) {
        this.initializationVector = initializationVector;
    }
}

