package pl.akmf.ksef.sdk.client.interfaces;

import pl.akmf.ksef.sdk.client.model.ApiException;

public interface QrCodeService {

    /**
     * Generuje kod QR jako tablicę bajtów PNG.
     *
     * @param payloadUrl           - URL/link do zakodowania.
     * @param pixelsPerModule      - Rozmiar modułu w pikselach (domyślnie 20).
     * @param qrCodeWidthAndHeight - Rozmiar obrazka w pikselach (domyślnie 300).
     * @return
     */
    byte[] generateQrCode(String payloadUrl, int pixelsPerModule, int qrCodeWidthAndHeight) throws ApiException;

    byte[] generateQrCode(String payloadUrl) throws ApiException;

    /**
     * Dokleja podpis (label) pod istniejącym PNG z kodem QR.
     *
     * @param qrCodePng
     * @param label
     * @param fontSizePx - rozmiar czcionki w pikselach (domyślnie 14).
     * @param fontName - nazwa czcionki (domyślnie Arial).
     * @return
     */
    byte[] addLabelToQrCode(byte[] qrCodePng, String label, int fontSizePx, String fontName) throws ApiException;

    byte[] addLabelToQrCode(byte[] qrCodePng, String label) throws ApiException;
}
