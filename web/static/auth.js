(() => {
    "use strict";

    const requestForm = document.getElementById("request-code-form");
    const verifyForm = document.getElementById("verify-code-form");
    const identifierInput = document.getElementById("identifier");
    const otpInput = document.getElementById("otp-code");
    const requestButton = document.getElementById("request-button");
    const verifyButton = document.getElementById("verify-button");
    const resendButton = document.getElementById("resend-button");
    const resendTimer = document.getElementById("resend-timer");
    const requestError = document.getElementById("request-error");
    const requestInfo = document.getElementById("request-info");
    const verifyError = document.getElementById("verify-error");
    const cantLoginButton = document.getElementById("cant-login-button");
    const recoveryNote = document.getElementById("recovery-note");

    let activeIdentifier = "";
    let activeChannel = "";
    let resendInterval = null;

    function showMessage(element, message) {
        element.textContent = message;
        element.hidden = false;
    }

    function clearMessage(element) {
        element.textContent = "";
        element.hidden = true;
    }

    async function responseMessage(response, fallback) {
        try {
            const body = await response.json();
            return body.detail || body.message || fallback;
        } catch {
            return fallback;
        }
    }

    function selectedChannel(identifier) {
        return identifier.includes("@") ? "email" : "phone";
    }

    function startResendTimer() {
        let secondsRemaining = 30;
        resendButton.disabled = true;
        resendTimer.textContent = `Повторный запрос через ${secondsRemaining} сек.`;
        if (resendInterval !== null) {
            window.clearInterval(resendInterval);
        }
        resendInterval = window.setInterval(() => {
            secondsRemaining -= 1;
            if (secondsRemaining <= 0) {
                window.clearInterval(resendInterval);
                resendInterval = null;
                resendButton.disabled = false;
                resendTimer.textContent = "Можно запросить новый код.";
                return;
            }
            resendTimer.textContent = `Повторный запрос через ${secondsRemaining} сек.`;
        }, 1000);
    }

    async function requestCode() {
        const identifier = activeIdentifier.trim();
        activeChannel = selectedChannel(identifier);
        const contactPattern = activeChannel === "email"
            ? /^[^\s@]+@[^\s@]+\.[^\s@]+$/
            : /^\+?[0-9\s().-]{7,20}$/;
        if (!contactPattern.test(identifier)) {
            throw new Error(
                activeChannel === "email"
                    ? "Проверьте адрес email."
                    : "Проверьте номер телефона."
            );
        }

        const response = await fetch("/auth/request-code", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            credentials: "same-origin",
            body: JSON.stringify({identifier, channel: activeChannel}),
        });
        if (!response.ok) {
            throw new Error(await responseMessage(response, "Не удалось запросить код."));
        }

        requestForm.hidden = true;
        verifyForm.hidden = false;
        clearMessage(requestError);
        showMessage(
            requestInfo,
            "Если аккаунт существует, код будет отправлен на указанный контакт."
        );
        otpInput.value = "";
        otpInput.focus();
        startResendTimer();
    }

    if (requestForm && verifyForm) {
        requestForm.addEventListener("submit", async (event) => {
            event.preventDefault();
            activeIdentifier = identifierInput.value.trim();
            clearMessage(requestError);
            clearMessage(requestInfo);
            requestButton.disabled = true;
            try {
                await requestCode();
            } catch (error) {
                showMessage(
                    requestError,
                    error instanceof Error ? error.message : "Не удалось запросить код."
                );
            } finally {
                requestButton.disabled = false;
            }
        });

        verifyForm.addEventListener("submit", async (event) => {
            event.preventDefault();
            clearMessage(verifyError);
            if (!otpInput.checkValidity()) {
                otpInput.reportValidity();
                return;
            }
            verifyButton.disabled = true;
            try {
                const response = await fetch("/auth/verify-code", {
                    method: "POST",
                    headers: {"Content-Type": "application/json"},
                    credentials: "same-origin",
                    body: JSON.stringify({
                        identifier: activeIdentifier,
                        channel: activeChannel,
                        code: otpInput.value,
                    }),
                });
                if (!response.ok) {
                    throw new Error(await responseMessage(
                        response,
                        "Код неверный или срок его действия истёк."
                    ));
                }
                window.location.assign("/dashboard");
            } catch (error) {
                showMessage(
                    verifyError,
                    error instanceof Error ? error.message : "Не удалось проверить код."
                );
            } finally {
                verifyButton.disabled = false;
            }
        });

        otpInput.addEventListener("input", () => {
            otpInput.value = otpInput.value.replace(/\D/g, "").slice(0, 6);
        });

        resendButton.addEventListener("click", async () => {
            resendButton.disabled = true;
            clearMessage(verifyError);
            try {
                await requestCode();
            } catch (error) {
                resendButton.disabled = false;
                showMessage(
                    verifyError,
                    error instanceof Error ? error.message : "Не удалось отправить код."
                );
            }
        });

        cantLoginButton.addEventListener("click", () => {
            recoveryNote.hidden = !recoveryNote.hidden;
            if (!requestForm.hidden) {
                identifierInput.focus();
            } else {
                requestForm.hidden = false;
                verifyForm.hidden = true;
                clearMessage(verifyError);
                identifierInput.focus();
            }
        });
    }

    function blank(value) {
        if (value === null || value === undefined || value === "") {
            return "—";
        }
        return String(value);
    }

    function yesNo(value) {
        return value ? "да" : "нет";
    }

    function partnerName(partner) {
        const parts = [partner.first_name, partner.last_name].filter(
            (part) => part
        );
        return parts.length ? parts.join(" ") : "—";
    }

    function showAdminPartners() {
        const section = document.getElementById("admin-partners");
        const status = document.getElementById("admin-partners-status");
        const denied = document.getElementById("admin-partners-denied");
        const panel = document.getElementById("admin-partners-panel");
        const body = document.getElementById("admin-partners-body");
        const empty = document.getElementById("admin-partners-empty");
        const pageLabel = document.getElementById("admin-partners-page");
        const previous = document.getElementById("admin-partners-prev");
        const next = document.getElementById("admin-partners-next");
        const pageSize = 50;
        let offset = 0;
        let total = 0;

        section.hidden = false;
        document.querySelector(".dashboard-shell").classList.add("admin-open");

        function setStatus(text, isError) {
            status.hidden = false;
            status.textContent = text;
            status.classList.toggle("error", isError);
            status.classList.toggle("info", !isError);
        }

        function hideAdminData() {
            panel.hidden = true;
            body.replaceChildren();
            empty.hidden = true;
        }

        async function loadPage() {
            denied.hidden = true;
            panel.hidden = true;
            empty.hidden = true;
            setStatus("Загружаем список партнёров…", false);
            previous.disabled = true;
            next.disabled = true;
            const response = await fetch(
                `/admin/partners?limit=${pageSize}&offset=${offset}`,
                {credentials: "same-origin"}
            );
            if (response.status === 401) {
                window.location.replace("/login");
                return;
            }
            if (response.status === 403) {
                status.hidden = true;
                hideAdminData();
                denied.hidden = false;
                return;
            }
            if (!response.ok) {
                hideAdminData();
                setStatus("Не удалось загрузить список партнёров.", true);
                return;
            }
            const payload = await response.json();
            total = payload.total;
            body.replaceChildren();
            status.hidden = true;
            if (!payload.items.length) {
                panel.hidden = false;
                empty.hidden = false;
            } else {
                payload.items.forEach((partner) => {
                    const row = document.createElement("tr");
                    [
                        partner.id,
                        partnerName(partner),
                        blank(partner.email),
                        blank(partner.phone),
                        blank(partner.role),
                        blank(partner.status),
                        blank(partner.root_id),
                        blank(partner.upline_id),
                        yesNo(partner.is_permanent_root),
                        yesNo(partner.is_active),
                    ].forEach((value) => {
                        const cell = document.createElement("td");
                        cell.textContent = blank(value);
                        row.appendChild(cell);
                    });
                    body.appendChild(row);
                });
                panel.hidden = false;
                empty.hidden = true;
            }
            const from = total === 0 ? 0 : offset + 1;
            const to = Math.min(offset + payload.items.length, total);
            pageLabel.textContent = total === 0
                ? "0 из 0"
                : `${from}–${to} из ${total}`;
            previous.disabled = offset === 0;
            next.disabled = offset + pageSize >= total;
        }

        previous.addEventListener("click", () => {
            offset = Math.max(0, offset - pageSize);
            loadPage().catch(() => {
                hideAdminData();
                setStatus("Не удалось загрузить список партнёров.", true);
            });
        });
        next.addEventListener("click", () => {
            offset += pageSize;
            loadPage().catch(() => {
                hideAdminData();
                setStatus("Не удалось загрузить список партнёров.", true);
            });
        });
        loadPage().catch(() => {
            hideAdminData();
            setStatus("Не удалось загрузить список партнёров.", true);
        });
    }

    const details = document.getElementById("partner-details");
    if (details) {
        const message = document.getElementById("dashboard-message");
        const logoutButton = document.getElementById("logout-button");
        fetch("/auth/me", {credentials: "same-origin"})
            .then(async (response) => {
                if (response.status === 401) {
                    window.location.replace("/login");
                    return null;
                }
                if (!response.ok) {
                    throw new Error("Не удалось загрузить данные кабинета.");
                }
                return response.json();
            })
            .then((partner) => {
                if (!partner) {
                    return;
                }
                document.getElementById("partner-name").textContent =
                    `Партнёр #${partner.id}`;
                document.getElementById("partner-email").textContent =
                    partner.email || "Не указан";
                document.getElementById("partner-phone").textContent =
                    partner.phone || "Не указан";
                document.getElementById("partner-referral-code").textContent =
                    partner.referral_code || "—";
                document.getElementById("partner-root-id").textContent =
                    partner.root_id ?? "—";
                details.hidden = false;
                message.hidden = true;
                if (partner.role === "admin") {
                    showAdminPartners();
                }
            })
            .catch(() => {
                showMessage(message, "Не удалось загрузить кабинет. Попробуйте обновить страницу.");
            });

        logoutButton.addEventListener("click", async () => {
            logoutButton.disabled = true;
            try {
                await fetch("/auth/logout", {
                    method: "POST",
                    credentials: "same-origin",
                });
            } finally {
                window.location.replace("/login");
            }
        });
    }
})();
