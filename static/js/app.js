const menuButton = document.querySelector(".menu-button");
const siteNav = document.querySelector("#site-nav");

if (menuButton && siteNav) {
    menuButton.addEventListener("click", () => {
        const isOpen = siteNav.classList.toggle("open");
        menuButton.setAttribute("aria-expanded", String(isOpen));
    });

    siteNav.addEventListener("click", (event) => {
        if (event.target.closest("a") && window.innerWidth <= 900) {
            siteNav.classList.remove("open");
            menuButton.setAttribute("aria-expanded", "false");
        }
    });
}

document.querySelectorAll(".flash-close").forEach((button) => {
    button.addEventListener("click", () => button.closest(".flash")?.remove());
});

document.querySelectorAll(".password-toggle").forEach((button) => {
    button.addEventListener("click", () => {
        const input = button.closest(".password-field")?.querySelector("input");
        if (!input) return;
        const shouldShow = input.type === "password";
        input.type = shouldShow ? "text" : "password";
        button.textContent = shouldShow ? "Hide" : "Show";
    });
});

document.querySelectorAll("[data-character-count]").forEach((counter) => {
    const textarea = counter.closest("label")?.querySelector("textarea");
    if (!textarea) return;
    const update = () => {
        counter.textContent = String(textarea.value.length);
    };
    textarea.addEventListener("input", update);
    update();
});

document.querySelectorAll("[data-confirm]").forEach((control) => {
    control.addEventListener("click", (event) => {
        if (!window.confirm(control.dataset.confirm || "Are you sure?")) {
            event.preventDefault();
        }
    });
});

const exchangeForm = document.querySelector("[data-exchange-form]");
if (exchangeForm) {
    const radios = exchangeForm.querySelectorAll('input[name="mode"]');
    const offeredWrapper = exchangeForm.querySelector("[data-offered-skill]");
    const offeredSelect = offeredWrapper?.querySelector("select");

    const updateExchangeMode = () => {
        const selected = exchangeForm.querySelector('input[name="mode"]:checked');
        const isSwap = selected?.value === "swap";
        if (offeredWrapper) offeredWrapper.hidden = !isSwap;
        if (offeredSelect) offeredSelect.required = Boolean(isSwap);
    };

    radios.forEach((radio) => radio.addEventListener("change", updateExchangeMode));
    updateExchangeMode();
}

const messageThread = document.querySelector("[data-message-thread]");
if (messageThread) {
    messageThread.scrollTop = messageThread.scrollHeight;
}
