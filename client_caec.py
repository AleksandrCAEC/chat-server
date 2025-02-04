<script>
document.addEventListener("DOMContentLoaded", function () {
    const chatHeader = document.getElementById("chat-header");
    const chatBody = document.getElementById("chat-body");
    const chatMessages = document.getElementById("chat-messages");
    const chatInput = document.getElementById("chat-input");
    const chatSend = document.getElementById("chat-send");
    const registerBtn = document.getElementById("register-btn");
    const nameInput = document.getElementById("name-input");
    const phoneInput = document.getElementById("phone-input");
    const emailInput = document.getElementById("email-input");
    const codeInput = document.getElementById("code-input");
    const chatFeedback = document.getElementById("chat-feedback");
    const registrationForm = document.getElementById("registration-form");
    const messageForm = document.getElementById("message-form");
    const languageSelection = document.getElementById("language-selection");
    const englishBtn = document.getElementById("english-btn");
    const russianBtn = document.getElementById("russian-btn");
    const serverUrl = "https://chat-server-704864345614.us-central1.run.app";

    // Элементы подсказок под полями
    const phoneHint = document.getElementById("phone-hint");
    const emailHint = document.getElementById("email-hint");
    const codeHint = document.getElementById("code-hint");

    let selectedLanguage = ""; // Для хранения выбранного языка
    let uniqueCode = ""; // Для хранения уникального кода клиента

    // Переключение отображения чата
    chatHeader.addEventListener("click", () => {
        chatBody.style.display = chatBody.style.display === "none" ? "block" : "none";
    });

    // Выбор языка (английский)
    englishBtn.addEventListener("click", () => {
        selectedLanguage = "en";
        languageSelection.style.display = "none";
        registrationForm.style.display = "block";

        // Устанавливаем placeholder'ы и значения по умолчанию
        nameInput.placeholder = "Enter your name";
        phoneInput.placeholder = "Your phone";
        emailInput.placeholder = "Your e-mail";
        codeInput.placeholder = "CAEC unique code";
        registerBtn.textContent = "REGISTER";
        chatInput.placeholder = "Enter your message...";
        chatSend.textContent = "SEND";

        // Устанавливаем подсказки под полями для английской версии
        phoneHint.innerText = "Enter your phone number with international code";
        emailHint.innerText = "Enter your e-mail";
        codeHint.innerText = "If you already have a unique CAEC code, enter it for simplified login.";

        // Предустанавливаем символы для облегчения ввода
        phoneInput.value = '+';
        emailInput.value = '@';
    });

    // Выбор языка (русский)
    russianBtn.addEventListener("click", () => {
        selectedLanguage = "ru";
        languageSelection.style.display = "none";
        registrationForm.style.display = "block";

        // Устанавливаем placeholder'ы и значения по умолчанию
        nameInput.placeholder = "Введите ваше имя";
        phoneInput.placeholder = "Ваш телефон";
        emailInput.placeholder = "Ваш e-mail";
        codeInput.placeholder = "Уникальный код CAEC";
        registerBtn.textContent = "ЗАРЕГИСТРИРОВАТЬСЯ";
        chatInput.placeholder = "Введите сообщение...";
        chatSend.textContent = "ОТПРАВИТЬ";

        // Устанавливаем подсказки под полями для русской версии
        phoneHint.innerText = "Укажите номер телефона с международным кодом";
        emailHint.innerText = "Укажите Ваш e-mail";
        codeHint.innerText = "Если у вас уже есть уникальный код CAEC, укажите его для упрощения входа.";

        // Предустанавливаем символы для облегчения ввода
        phoneInput.value = '+';
        emailInput.value = '@';
    });

    // Регистрация клиента
    registerBtn.addEventListener("click", () => {
        const name = nameInput.value.trim();
        const phone = phoneInput.value.trim();
        const email = emailInput.value.trim();
        const code = codeInput.value.trim();

        // Проверка на пустые поля
        if (!code && (!name || !phone || !email)) {
            showError(
                selectedLanguage === "en"
                    ? "Please fill out all required fields for registration."
                    : "Заполните все необходимые поля для регистрации."
            );
            return;
        }

        // Проверка валидации
        if (!code) {
            if (!phone.startsWith("+")) {
                showError(
                    selectedLanguage === "en"
                        ? "Phone number must start with +."
                        : "Номер телефона должен начинаться с +."
                );
                return;
            }

            if (!email.includes("@")) {
                showError(
                    selectedLanguage === "en"
                        ? "Email must contain @."
                        : "Email должен содержать @."
                );
                return;
            }
        }

        // Блокируем кнопку и меняем текст
        registerBtn.disabled = true;
        registerBtn.textContent = selectedLanguage === "en" ? "Please wait..." : "ПОДОЖДИТЕ...";

        if (code) {
            // Вход по коду
            fetch(`${serverUrl}/verify-code`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({ code }),
            })
                .then((response) => response.json())
                .then((data) => {
                    if (data.status === "success") {
                        const userData = data.clientData;
                        uniqueCode = code;
                        sendTelegramNotification(
                            `Returning user logged in:\nName: ${userData.Name}\nPhone: ${userData.Phone}\nEmail: ${userData.Email}\nCode: ${code}`
                        );

                        showMessageForm();
                        appendMessage(
                            "CAEC",
                            selectedLanguage === "en"
                                ? `Dear, ${userData.Name}, hello. Thank you for returning.<br><br>How can we assist you?`
                                : `Уважаемый, ${userData.Name}, здравствуйте. Спасибо, что вернулись.<br><br>Чем можем быть полезны?`
                        );
                    } else {
                        showError(
                            selectedLanguage === "en"
                                ? "Invalid code. Please try again."
                                : "Неверный код. Проверьте и попробуйте снова."
                        );
                    }
                })
                .catch(() =>
                    showError(
                        selectedLanguage === "en"
                            ? "Connection error."
                            : "Ошибка соединения с сервером."
                    )
                )
                .finally(() => {
                    registerBtn.disabled = false;
                    registerBtn.textContent = selectedLanguage === "en" ? "REGISTER" : "ЗАРЕГИСТРИРОВАТЬСЯ";
                });
        } else {
            // Регистрация нового клиента
            fetch(`${serverUrl}/register-client`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({ name, phone, email }),
            })
                .then((response) => response.json())
                .then((data) => {
                    if (data.uniqueCode) {
                        uniqueCode = data.uniqueCode;
                        sendTelegramNotification(
                            `New user registered:\nName: ${name}\nPhone: ${phone}\nEmail: ${email}\nCode: ${uniqueCode}`
                        );

                        showMessageForm();
                        appendMessage(
                            "CAEC",
                            selectedLanguage === "en"
                                ? `Dear, ${name}, you are registered in the customer database of CAEC GmbH. Assigned code: <strong>${uniqueCode}</strong>. Please remember this code for re-login to save the fine-tuned communication settings and your needs in the future. Thank you.<br><br>How can we assist you?`
                                : `Уважаемый, ${name}, вы зарегистрированы в клиентской базе данных компании CAEC GmbH. Присвоенный код: <strong>${uniqueCode}</strong>. Пожалуйста, запомните этот код для повторного входа в систему, чтобы сохранить тонкие настройки на коммуникацию и ваши потребности в будущем. Спасибо.<br><br>Чем можем быть полезны?`
                        );
                    } else {
                        showError(
                            data.message ||
                                (selectedLanguage === "en"
                                    ? "Registration error."
                                    : "Ошибка регистрации.")
                        );
                    }
                })
                .catch((error) => {
                    console.error("Ошибка регистрации:", error);
                    showError(
                        selectedLanguage === "en"
                            ? "Connection error."
                            : "Ошибка соединения с сервером."
                    );
                })
                .finally(() => {
                    registerBtn.disabled = false;
                    registerBtn.textContent = selectedLanguage === "en" ? "REGISTER" : "ЗАРЕГИСТРИРОВАТЬСЯ";
                });
        }
    });

    function sendTelegramNotification(message) {
        fetch(`${serverUrl}/send-telegram`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({ message }),
        }).catch((error) => console.error("Ошибка Telegram:", error));
    }

    function showMessageForm() {
        registrationForm.style.display = "none";
        messageForm.style.display = "block";
        chatMessages.style.display = "block";
    }

    chatSend.addEventListener("click", () => sendMessage());
    chatInput.addEventListener("keypress", (event) => {
        if (event.key === "Enter") {
            event.preventDefault();
            sendMessage();
        }
    });

    function sendMessage() {
        const userMessage = chatInput.value.trim();
        if (!userMessage) return;

        chatSend.disabled = true;
        chatSend.textContent = selectedLanguage === "en" ? "Please wait..." : "ПОДОЖДИТЕ...";

        appendMessage(selectedLanguage === "en" ? "You" : "Вы", userMessage);
        chatInput.value = "";

        fetch(`${serverUrl}/chat`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({ message: userMessage, client_code: uniqueCode }),
        })
            .then((response) => response.json())
            .then((data) => {
                appendMessage(
                    "CAEC",
                    data.reply || (selectedLanguage === "en" ? "Error retrieving response." : "Ошибка получения ответа.")
                );
            })
            .catch((error) => {
                console.error("Ошибка отправки сообщения:", error);
                showError(
                    selectedLanguage === "en"
                        ? "Connection error."
                        : "Ошибка соединения с сервером."
                );
            })
            .finally(() => {
                chatSend.disabled = false;
                chatSend.textContent = selectedLanguage === "en" ? "SEND" : "ОТПРАВИТЬ";
            });
    }

    function appendMessage(sender, message) {
        const messageElement = document.createElement("div");
        messageElement.style.marginBottom = "10px";
        messageElement.innerHTML = `<strong>${sender}:</strong> ${message}`;
        chatMessages.appendChild(messageElement);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    function showError(message) {
        chatFeedback.style.display = "block";
        chatFeedback.textContent = message;
        setTimeout(() => {
            chatFeedback.style.display = "none";
        }, 3000);
    }
});
</script>
