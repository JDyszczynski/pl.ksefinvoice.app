package pl.akmf.ksef.sdk.api.builders.session;

import pl.akmf.ksef.sdk.client.model.session.EncryptionInfo;
import pl.akmf.ksef.sdk.client.model.session.FormCode;
import pl.akmf.ksef.sdk.client.model.session.online.OpenOnlineSessionRequest;

public class OpenOnlineSessionRequestBuilder {
    private FormCode formCode;
    private EncryptionInfo encryptionInfo;

    public OpenOnlineSessionRequestBuilder withFormCode(FormCode formCode) {
        this.formCode = formCode;
        return this;
    }

    public OpenOnlineSessionRequestBuilder withEncryptionInfo(EncryptionInfo encryptionInfo) {
        this.encryptionInfo = encryptionInfo;
        return this;
    }

    public OpenOnlineSessionRequest build() {
        return new OpenOnlineSessionRequest(formCode, encryptionInfo);
    }
}
