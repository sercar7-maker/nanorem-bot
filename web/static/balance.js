(() => {
    "use strict";
    const details = document.getElementById("balance-details");
    if (!details) return;
    const message = document.getElementById("balance-message");
    const refresh = document.getElementById("balance-refresh");
    const fields = ["available", "reserved", "total"];

    async function loadBalance() {
        refresh.disabled = true;
        details.hidden = true;
        fields.forEach((field) => {
            document.getElementById(`balance-${field}`).textContent = "";
        });
        message.hidden = false;
        message.classList.remove("error");
        message.textContent = "Загружаем баланс…";
        try {
            const response = await fetch("/auth/me/balance", {
                credentials: "same-origin",
                cache: "no-store",
            });
            if (response.status === 401) {
                window.location.replace("/login");
                return;
            }
            if (!response.ok) throw new Error("Balance unavailable");
            const balance = await response.json();
            if (balance.currency !== "RUB" || fields.some((field) =>
                typeof balance[field] !== "string" || !/^-?[0-9]+\.[0-9]{2}$/.test(balance[field])
            )) throw new Error("Invalid balance response");
            fields.forEach((field) => {
                document.getElementById(`balance-${field}`).textContent =
                    `${balance[field].replace(".", ",")} ₽`;
            });
            details.hidden = false;
            message.hidden = true;
        } catch {
            message.classList.add("error");
            message.textContent = "Не удалось загрузить баланс. Нажмите «Обновить баланс».";
        } finally {
            refresh.disabled = false;
        }
    }

    refresh.addEventListener("click", loadBalance);
    loadBalance();
})();
