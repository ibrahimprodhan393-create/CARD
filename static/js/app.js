(() => {
  const body = document.body;
  const cartKey = "russian-market-cart";

  const savedTheme = localStorage.getItem("russian-market-theme");
  if (savedTheme === "dark") {
    body.classList.add("dark-theme");
  }

  document.addEventListener("click", async (event) => {
    const userTab = event.target.closest("[data-section-tab]");
    if (userTab) {
      showUserSection(userTab.dataset.sectionTab);
      localStorage.setItem("russian-market-user-section", userTab.dataset.sectionTab);
      return;
    }

    const adminTab = event.target.closest("[data-admin-tab]");
    if (adminTab) {
      showAdminSection(adminTab.dataset.adminTab);
      localStorage.setItem("russian-market-admin-section", adminTab.dataset.adminTab);
      return;
    }

    const networkTab = event.target.closest("[data-network-filter]");
    if (networkTab) {
      document.querySelectorAll("[data-network-filter]").forEach((button) => {
        button.classList.toggle("active", button === networkTab);
      });
      filterCards();
      return;
    }

    const addCart = event.target.closest("[data-add-cart]");
    if (addCart) {
      const card = addCart.closest("[data-card]");
      const quantity = Math.max(1, Number(card.querySelector("[data-card-qty]")?.value || 1));
      upsertCart({
        id: card.dataset.cardId,
        title: card.dataset.title,
        country: card.dataset.country,
        network: card.dataset.networkName || card.dataset.network,
        price: Number(card.dataset.price || 0),
        quantity,
      });
      showUserSection("cart");
      return;
    }

    const removeCart = event.target.closest("[data-remove-cart]");
    if (removeCart) {
      const id = removeCart.dataset.removeCart;
      saveCart(getCart().filter((item) => item.id !== id));
      renderCart();
      return;
    }

    const buyCart = event.target.closest("[data-buy-cart]");
    if (buyCart) {
      const id = buyCart.dataset.buyCart;
      const item = getCart().find((entry) => entry.id === id);
      if (!item) return;
      if (!window.confirm("Confirm purchase?")) {
        return;
      }
      saveCart(getCart().filter((entry) => entry.id !== id));
      submitPurchase(item);
      return;
    }

    const openButton = event.target.closest("[data-open-modal]");
    if (openButton) {
      const modal = document.getElementById(openButton.dataset.openModal);
      if (modal) {
        modal.classList.remove("is-hidden");
      }
      return;
    }

    const closeButton = event.target.closest("[data-close-modal]");
    if (closeButton) {
      const modal = document.getElementById(closeButton.dataset.closeModal);
      if (modal) {
        modal.classList.add("is-hidden");
      }
      return;
    }

    const modalBackdrop = event.target.classList.contains("modal-backdrop")
      ? event.target
      : null;
    if (modalBackdrop) {
      modalBackdrop.classList.add("is-hidden");
      return;
    }

    const themeButton = event.target.closest("[data-theme-toggle]");
    if (themeButton) {
      body.classList.toggle("dark-theme");
      localStorage.setItem(
        "russian-market-theme",
        body.classList.contains("dark-theme") ? "dark" : "light"
      );
      return;
    }

    const copyButton = event.target.closest("[data-copy]");
    if (copyButton) {
      const text = copyButton.dataset.copy;
      try {
        await navigator.clipboard.writeText(text);
        const previous = copyButton.textContent;
        copyButton.textContent = "Copied";
        setTimeout(() => {
          copyButton.textContent = previous;
        }, 1200);
      } catch (error) {
        copyButton.textContent = "Copy failed";
      }
    }

    const passwordToggle = event.target.closest("[data-toggle-password]");
    if (passwordToggle) {
      const input = passwordToggle.closest(".password-field")?.querySelector("input");
      if (!input) return;
      const visible = input.type === "text";
      input.type = visible ? "password" : "text";
      passwordToggle.classList.toggle("is-visible", !visible);
      passwordToggle.setAttribute("aria-label", visible ? "Show password" : "Hide password");
      return;
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") {
      return;
    }
    document.querySelectorAll(".modal-backdrop:not(.is-hidden)").forEach((modal) => {
      modal.classList.add("is-hidden");
    });
  });

  document.querySelector("[data-card-search]")?.addEventListener("input", filterCards);

  function showUserSection(name) {
    document.querySelectorAll("[data-section-tab]").forEach((button) => {
      button.classList.toggle("active", button.dataset.sectionTab === name);
    });
    document.querySelectorAll("[data-user-section]").forEach((section) => {
      section.classList.toggle("active", section.dataset.userSection === name);
    });
  }

  function showAdminSection(name) {
    document.querySelectorAll("[data-admin-tab]").forEach((button) => {
      button.classList.toggle("active", button.dataset.adminTab === name);
    });
    document.querySelectorAll("[data-admin-section]").forEach((section) => {
      section.classList.toggle("active", section.dataset.adminSection === name);
    });
  }

  function activeNetwork() {
    return document.querySelector("[data-network-filter].active")?.dataset.networkFilter || "all";
  }

  function filterCards() {
    const term = (document.querySelector("[data-card-search]")?.value || "").toLowerCase();
    const network = activeNetwork();
    document.querySelectorAll("[data-card]").forEach((card) => {
      const text = (card.dataset.title || "").toLowerCase();
      const cardNetwork = card.dataset.network || "";
      const matchesText = !term || text.includes(term);
      const matchesNetwork = network === "all" || cardNetwork === network;
      card.hidden = !(matchesText && matchesNetwork);
    });
  }

  function getCart() {
    try {
      return JSON.parse(localStorage.getItem(cartKey) || "[]");
    } catch {
      return [];
    }
  }

  function saveCart(cart) {
    localStorage.setItem(cartKey, JSON.stringify(cart));
  }

  function upsertCart(item) {
    const cart = getCart();
    const index = cart.findIndex((entry) => entry.id === item.id);
    if (index >= 0) {
      cart[index].quantity += item.quantity;
    } else {
      cart.push(item);
    }
    saveCart(cart);
    renderCart();
  }

  function renderCart() {
    const cart = getCart();
    const list = document.querySelector("[data-cart-list]");
    const empty = document.querySelector("[data-cart-empty]");
    const count = document.querySelector("[data-cart-count]");
    if (count) {
      count.textContent = String(cart.reduce((total, item) => total + item.quantity, 0));
    }
    if (!list) return;
    list.innerHTML = "";
    empty?.toggleAttribute("hidden", cart.length > 0);
    cart.forEach((item) => {
      const row = document.createElement("article");
      row.className = "cart-item";
      row.innerHTML = `
        <div>
          <strong>${escapeHtml(item.country)} ${escapeHtml(item.network)}</strong>
          <span>Qty ${item.quantity} - $${(item.price * item.quantity).toFixed(2)}</span>
        </div>
        <div class="cart-actions">
          <button class="small-button" type="button" data-buy-cart="${item.id}">Buy</button>
          <button class="icon-button" type="button" data-remove-cart="${item.id}">Remove</button>
        </div>
      `;
      list.appendChild(row);
    });
  }

  function submitPurchase(item) {
    const form = document.createElement("form");
    form.method = "post";
    form.action = `/purchase/${encodeURIComponent(item.id)}`;
    const input = document.createElement("input");
    input.type = "hidden";
    input.name = "quantity";
    input.value = String(item.quantity);
    form.appendChild(input);
    document.body.appendChild(form);
    form.submit();
  }

  function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, (char) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#039;",
    }[char]));
  }

  async function setupLiveRefresh() {
    const endpoint = document.querySelector(".admin-shell")
      ? "/api/admin/status"
      : document.querySelector(".phone-shell")
        ? "/api/user/status"
        : null;
    if (!endpoint) return;
    let lastVersion = null;
    const check = async () => {
      if (document.hidden) return;
      if (document.querySelector(".modal-backdrop:not(.is-hidden)")) return;
      if (document.activeElement && ["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName)) return;
      try {
        const response = await fetch(endpoint, { cache: "no-store" });
        if (!response.ok) return;
        const data = await response.json();
        if (lastVersion && data.version !== lastVersion) {
          window.location.reload();
          return;
        }
        lastVersion = data.version;
      } catch {
        return;
      }
    };
    await check();
    setInterval(check, 4000);
  }

  renderCart();
  filterCards();
  const storedUserSection = localStorage.getItem("russian-market-user-section");
  if (storedUserSection && document.querySelector(`[data-user-section="${storedUserSection}"]`)) {
    showUserSection(storedUserSection);
  }
  const storedAdminSection = localStorage.getItem("russian-market-admin-section");
  if (storedAdminSection && document.querySelector(`[data-admin-section="${storedAdminSection}"]`)) {
    showAdminSection(storedAdminSection);
  }
  setupLiveRefresh();
})();
