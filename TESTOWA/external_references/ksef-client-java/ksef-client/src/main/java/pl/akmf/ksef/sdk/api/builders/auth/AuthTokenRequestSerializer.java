package pl.akmf.ksef.sdk.api.builders.auth;

import jakarta.xml.bind.JAXBContext;
import jakarta.xml.bind.JAXBException;
import jakarta.xml.bind.Marshaller;
import pl.akmf.ksef.sdk.client.model.xml.AuthTokenRequest;

import java.io.StringWriter;

public class AuthTokenRequestSerializer {

    private AuthTokenRequestSerializer() {
    }

    public static String authTokenRequestSerializer(AuthTokenRequest authTokenRequest) throws JAXBException {
        JAXBContext jc = JAXBContext.newInstance(AuthTokenRequest.class);

        Marshaller marshaller = jc.createMarshaller();
        marshaller.setProperty(Marshaller.JAXB_FORMATTED_OUTPUT, true);
        StringWriter result = new StringWriter();

        marshaller.marshal(authTokenRequest, result);

        return result.toString();
    }
}
