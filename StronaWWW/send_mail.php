<?php
// send_mail.php - Obsługa formularzy kontaktowego i zgłaszania błędów

// Konfiguracja
$recipient_email = "jarek@dyszczynski.pl"; // Zmień na właściwy adres email
$sender_email = "no-reply@ksefinvoice.pl"; // Adres, z którego będą wysyłane wiadomości (musi być zgodny z domeną serwera)

header('Content-Type: application/json');

// Funkcja pomocnicza do wysyłania odpowiedzi JSON
function send_response($success, $message) {
    echo json_encode(['success' => $success, 'message' => $message]);
    exit;
}

// Sprawdź metodę żądania
if ($_SERVER["REQUEST_METHOD"] != "POST") {
    send_response(false, "Dozwolone są tylko żądania POST.");
}

// 1. Ochrona przed botami (Honeypot)
if (!empty($_POST['website'])) {
    // Jeśli pole 'website' jest wypełnione, to jest to bot
    send_response(true, "Wiadomość wysłana pomyślnie."); // Fałszywy sukces dla bota
}

// 2. Ochrona przed botami (Time Trap & JS Token)
$min_seconds = 3;
$timestamp = isset($_POST['timestamp']) ? intval($_POST['timestamp']) : 0;
$current_time = time();

if ($timestamp == 0 || ($current_time - $timestamp) < $min_seconds) {
    // Zbyt szybkie wypełnienie formularza (bot) lub brak JS
    // Dla bota zwracamy błąd lub fałszywy sukces
    send_response(false, "Formularz wypełniono zbyt szybko. Jesteś robotem?");
}

if (!isset($_POST['spam_token']) || $_POST['spam_token'] !== 'ksef-secure-2026') {
     send_response(false, "Błąd weryfikacji anty-spamowej. Włącz JavaScript.");
}

// Pobierz i oczyść dane wejściowe
$form_type = isset($_POST['form_type']) ? $_POST['form_type'] : 'unknown';
$email = filter_var($_POST['email'], FILTER_SANITIZE_EMAIL);

if (!filter_var($email, FILTER_VALIDATE_EMAIL)) {
    send_response(false, "Podano niepoprawny adres email.");
}

$subject_prefix = "";
$email_body = "";
$headers = "From: " . $sender_email . "\r\n";
$headers .= "Reply-To: " . $email . "\r\n";
$headers .= "MIME-Version: 1.0\r\n";
$headers .= "Content-Type: text/plain; charset=UTF-8\r\n";

if ($form_type === 'contact') {
    // Formularz kontaktowy
    $name = htmlspecialchars($_POST['name']);
    $subject_input = htmlspecialchars($_POST['subject']);
    $message = htmlspecialchars($_POST['message']);

    $subject = "[KsefInvoice Kontakt] " . $subject_input;
    
    $email_body .= "Nowa wiadomość z formularza kontaktowego:\n\n";
    $email_body .= "Od: $name ($email)\n";
    $email_body .= "Temat: $subject_input\n\n";
    $email_body .= "Treść wiadomości:\n";
    $email_body .= $message . "\n";

} elseif ($form_type === 'bug_report') {
    // Zgłoszenie błędu
    $name = isset($_POST['name']) ? htmlspecialchars($_POST['name']) : 'Anonim';
    $os = htmlspecialchars($_POST['os']);
    $version = htmlspecialchars($_POST['version']);
    $summary = htmlspecialchars($_POST['summary']);
    $steps = htmlspecialchars($_POST['steps']);
    $logs = isset($_POST['logs']) ? htmlspecialchars($_POST['logs']) : '';

    $subject = "[KsefInvoice Bug] " . $summary;

    $email_body .= "Nowe zgłoszenie błędu:\n\n";
    $email_body .= "Zgłaszający: $name ($email)\n";
    $email_body .= "System: $os\n";
    $email_body .= "Wersja: $version\n";
    $email_body .= "Temat: $summary\n\n";
    $email_body .= "Kroki do odtworzenia:\n";
    $email_body .= $steps . "\n\n";
    
    if (!empty($logs)) {
        $email_body .= "Logi / Błędy:\n";
        $email_body .= $logs . "\n";
    }

} else {
    send_response(false, "Nieznany typ formularza.");
}

// Wysłanie maila
if (mail($recipient_email, $subject, $email_body, $headers)) {
    send_response(true, "Wiadomość została wysłana.");
} else {
    send_response(false, "Wystąpił błąd serwera podczas wysyłania wiadomości.");
}
?>