/* TCMAutoResearch — 登录页 Alpine 组件 */

function loginApp() {
  return {
    username: "",
    password: "",
    apiKey: "",
    apiKeyName: "",
    errorMsg: "",
    loading: false,
    showPwd: false,
    remember: false,
    loginMode: "password",
    destination: "dashboard",
    statusHint: "正在检测认证模式…",
    authConfig: {
      authRequired: true,
      authMode: "password",
      supportsPassword: true,
      supportsApiKey: false,
      guestAllowed: false,
    },

    async init() {
      // 读取目标落点 ?next=console 优先于本地默认
      const params = new URLSearchParams(window.location.search);
      if (params.get("next") === "console") {
        this.destination = "console";
      }

      // 已有 token：尝试静默续登，失败则清理并继续显示登录
      const existingToken = localStorage.getItem("access_token");
      if (existingToken) {
        try {
          const resp = await fetch("/api/auth/me", {
            headers: { Authorization: "Bearer " + existingToken },
          });
          if (resp.ok) {
            this.redirectAfterLogin();
            return;
          }
        } catch (_) {
          /* 忽略网络错误，走正常登录流程 */
        }
        localStorage.removeItem("access_token");
        localStorage.removeItem("token_type");
      }

      // 拉取认证模式
      try {
        const resp = await fetch("/api/auth/status");
        if (resp.ok) {
          const data = await resp.json();
          this.authConfig = {
            authRequired: data.auth_required,
            authMode: data.auth_mode,
            supportsPassword: data.supports_password_login,
            supportsApiKey: data.supports_api_key_login,
            guestAllowed: data.guest_allowed,
          };

          if (
            !this.authConfig.supportsPassword &&
            this.authConfig.supportsApiKey
          ) {
            this.loginMode = "api_key";
          }

          this.statusHint = this.computeStatusHint();
        } else {
          this.statusHint = "认证状态读取失败，请手动登录。";
        }
      } catch (_) {
        this.statusHint = "认证状态读取失败，请手动登录。";
      }

      // 自动聚焦首个输入，提升键盘可达性
      this.$nextTick(() => {
        const target =
          this.loginMode === "api_key"
            ? document.getElementById("apiKey")
            : document.getElementById("username");
        if (target) target.focus();
      });
    },

    computeStatusHint() {
      const mode = this.authConfig.authMode;
      if (mode === "password") {
        return "当前启用账号密码认证，登录后进入所选管理界面。";
      }
      if (mode === "management_api_key") {
        return "当前启用管理 API Key 认证，适合运维入口。";
      }
      if (this.authConfig.guestAllowed) {
        return "当前未配置认证，可直接以访客身份进入。";
      }
      return "请完成认证后继续。";
    },

    redirectAfterLogin() {
      if (this.destination === "console") {
        window.location.href = "/console";
      } else {
        window.location.href = "/dashboard";
      }
    },

    async doLogin(payload) {
      this.errorMsg = "";
      this.loading = true;
      try {
        const resp = await fetch("/api/auth/login", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });

        let data = {};
        try {
          data = await resp.json();
        } catch (_) {
          /* 服务端非 JSON 响应 */
        }

        if (!resp.ok) {
          // 后端 503：未配置用户 → 给出可执行指引
          if (resp.status === 503) {
            this.errorMsg =
              "系统尚未配置任何用户。请在 secrets.yml 的 security.console_auth.users 下添加用户后重启服务。";
          } else {
            this.errorMsg =
              data.detail || data.message || "登录失败，请检查凭证后重试";
          }
          return;
        }

        const token = data.access_token || data.token;
        if (token) {
          localStorage.setItem("access_token", token);
          localStorage.setItem("token_type", data.token_type || "bearer");
          if (data.display_name) {
            localStorage.setItem("display_name", data.display_name);
          }
        }

        this.redirectAfterLogin();
      } catch (_) {
        this.errorMsg = "网络错误，请检查连接后重试";
      } finally {
        this.loading = false;
      }
    },

    handlePasswordLogin() {
      if (!this.username.trim() || !this.password) {
        this.errorMsg = "请输入用户名和密码";
        return;
      }
      this.doLogin({
        username: this.username.trim(),
        password: this.password,
      });
    },

    handleApiKeyLogin() {
      if (!this.apiKey.trim()) {
        this.errorMsg = "请输入管理 API Key";
        return;
      }
      this.doLogin({
        username: this.apiKeyName.trim(),
        api_key: this.apiKey.trim(),
      });
    },

    handleGuestLogin() {
      localStorage.setItem("display_name", "访客");
      this.redirectAfterLogin();
    },
  };
}

// 暴露到全局供 Alpine x-data 使用
window.loginApp = loginApp;
