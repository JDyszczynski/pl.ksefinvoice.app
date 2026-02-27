package pl.akmf.ksef.sdk.client.model.session.online;

import pl.akmf.ksef.sdk.client.model.session.EncryptionInfo;
import pl.akmf.ksef.sdk.client.model.session.FormCode;

public class OpenOnlineSessionRequest {
    private FormCode formCode;
    private EncryptionInfo encryption;

    public OpenOnlineSessionRequest() {
    }

    public OpenOnlineSessionRequest(FormCode formCode, EncryptionInfo encryption) {
        this.formCode = formCode;
        this.encryption = encryption;
    }

    public FormCode getFormCode() {
        return formCode;
    }

    public void setFormCode(FormCode formCode) {
        this.formCode = formCode;
    }

    public EncryptionInfo getEncryption() {
        return encryption;
    }

    public void setEncryption(EncryptionInfo encryption) {
        this.encryption = encryption;
    }
}

