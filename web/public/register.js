/**
 * 用户注册页面 - 表单验证逻辑
 *
 * 功能：
 * 1. 表单字段验证（用户名、邮箱、密码、确认密码）
 * 2. 密码显示/隐藏切换
 * 3. 表单提交处理
 * 4. 提交按钮状态管理
 */

// ========== 状态管理 ==========
const state = {
  formData: {
    username: "",
    email: "",
    password: "",
    confirmPassword: "",
  },
  errors: {
    username: null,
    email: null,
    password: null,
    confirmPassword: null,
  },
  touched: {
    username: false,
    email: false,
    password: false,
    confirmPassword: false,
  },
  isSubmitting: false,
};

// ========== 验证器 ==========
const validators = {
  /**
   * 验证用户名
   * 规则：3-20 字符，仅字母、数字、下划线
   */
  username: (value) => {
    if (!value || value.trim() === "") {
      return "请输入用户名";
    }
    const regex = /^[a-zA-Z0-9_]{3,20}$/;
    if (!regex.test(value)) {
      return "用户名长度为 3-20 字符，仅支持字母、数字、下划线";
    }
    return null;
  },

  /**
   * 验证邮箱
   * 规则：符合邮箱格式
   */
  email: (value) => {
    if (!value || value.trim() === "") {
      return "请输入邮箱";
    }
    const regex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!regex.test(value)) {
      return "请输入有效的邮箱地址";
    }
    return null;
  },

  /**
   * 验证密码
   * 规则：至少 8 字符，包含大写字母、小写字母、数字
   */
  password: (value) => {
    if (!value || value.trim() === "") {
      return "请输入密码";
    }
    if (value.length < 8) {
      return "密码长度至少为 8 字符";
    }
    const hasUpper = /[A-Z]/.test(value);
    const hasLower = /[a-z]/.test(value);
    const hasNumber = /[0-9]/.test(value);
    if (!hasUpper || !hasLower || !hasNumber) {
      return "密码必须包含大写字母、小写字母和数字";
    }
    return null;
  },

  /**
   * 验证确认密码
   * 规则：与密码一致
   */
  confirmPassword: (value, password) => {
    if (!value || value.trim() === "") {
      return "请再次输入密码";
    }
    if (value !== password) {
      return "两次输入的密码不一致";
    }
    return null;
  },
};

// ========== 状态管理函数 ==========
/**
 * 验证单个字段
 */
function validateField(field) {
  const value = state.formData[field];
  if (field === "confirmPassword") {
    state.errors[field] = validators[field](value, state.formData.password);
  } else {
    state.errors[field] = validators[field](value);
  }
}

/**
 * 验证所有字段
 * @returns {boolean} 是否通过验证
 */
function validateAllFields() {
  validateField("username");
  validateField("email");
  validateField("password");
  validateField("confirmPassword");
  return !Object.values(state.errors).some((error) => error !== null);
}

/**
 * 检查表单是否可提交
 */
function isFormValid() {
  return (
    Object.values(state.formData).every((value) => value.trim() !== "") &&
    Object.values(state.errors).every((error) => error === null)
  );
}

// ========== UI 渲染函数 ==========
/**
 * 渲染单个字段的错误信息
 */
function renderFieldError(field) {
  const errorElement = document.getElementById(`${field}Error`);
  const inputElement = document.getElementById(field);

  if (state.errors[field] && state.touched[field]) {
    errorElement.textContent = state.errors[field];
    errorElement.style.display = "block";
    inputElement.classList.add("error");
  } else {
    errorElement.textContent = "";
    errorElement.style.display = "none";
    inputElement.classList.remove("error");
  }
}

/**
 * 更新提交按钮状态
 */
function updateSubmitButton() {
  const submitBtn = document.getElementById("submitBtn");
  const btnText = submitBtn.querySelector(".btn-text");
  const btnLoading = submitBtn.querySelector(".btn-loading");

  if (state.isSubmitting) {
    submitBtn.disabled = true;
    btnText.style.display = "none";
    btnLoading.style.display = "flex";
  } else {
    submitBtn.disabled = !isFormValid();
    btnText.style.display = "block";
    btnLoading.style.display = "none";
  }
}

// ========== 事件处理函数 ==========
/**
 * 处理输入框变化
 */
function handleInputChange(field, value) {
  state.formData[field] = value;
  validateField(field);

  // 如果密码改变，重新验证确认密码
  if (field === "password" && state.formData.confirmPassword) {
    validateField("confirmPassword");
    renderFieldError("confirmPassword");
  }

  // 如果是密码字段，更新密码强度
  if (field === "password") {
    updatePasswordStrength(value);
  }

  renderFieldError(field);
  updateSubmitButton();
}

/**
 * 计算密码强度
 * @param {string} password - 密码
 * @returns {Object} { strength: 'weak'|'medium'|'strong', rules: {...} }
 */
function calculatePasswordStrength(password) {
  const rules = {
    length: password.length >= 8,
    upper: /[A-Z]/.test(password),
    lower: /[a-z]/.test(password),
    number: /[0-9]/.test(password),
  };

  const satisfiedCount = Object.values(rules).filter(Boolean).length;

  let strength = "weak";
  if (satisfiedCount === 4) {
    strength = "strong";
  } else if (satisfiedCount >= 2) {
    strength = "medium";
  }

  return { strength, rules };
}

/**
 * 更新密码强度 UI
 * @param {string} password - 密码
 */
function updatePasswordStrength(password) {
  const strengthContainer = document.getElementById("passwordStrength");
  const strengthFill = document.getElementById("strengthFill");
  const strengthText = document.getElementById("strengthText");

  // 如果密码为空，隐藏强度提示
  if (!password) {
    strengthContainer.style.display = "none";
    return;
  }

  // 显示强度提示
  strengthContainer.style.display = "block";

  // 计算强度
  const { strength, rules } = calculatePasswordStrength(password);

  // 更新强度条
  strengthFill.className = `strength-fill ${strength}`;

  // 更新强度文字
  const strengthLabels = {
    weak: "弱",
    medium: "中",
    strong: "强",
  };
  strengthText.textContent = strengthLabels[strength];
  strengthText.className = `strength-text ${strength}`;

  // 更新规则清单
  const ruleElements = {
    length: document.getElementById("rule-length"),
    upper: document.getElementById("rule-upper"),
    lower: document.getElementById("rule-lower"),
    number: document.getElementById("rule-number"),
  };

  Object.keys(rules).forEach((key) => {
    const element = ruleElements[key];
    if (rules[key]) {
      element.classList.add("satisfied");
    } else {
      element.classList.remove("satisfied");
    }
  });
}

/**
 * 处理输入框失焦
 */
function handleInputBlur(field) {
  state.touched[field] = true;
  validateField(field);
  renderFieldError(field);
}

/**
 * 切换密码显示/隐藏
 */
function togglePasswordVisibility(inputId, buttonId) {
  const input = document.getElementById(inputId);
  const button = document.getElementById(buttonId);

  if (input.type === "password") {
    input.type = "text";
    button.classList.add("visible");
    button.setAttribute("aria-label", "隐藏密码");
  } else {
    input.type = "password";
    button.classList.remove("visible");
    button.setAttribute("aria-label", "显示密码");
  }
}

/**
 * 处理表单提交
 */
async function handleSubmit(event) {
  event.preventDefault();

  // 标记所有字段为已触摸
  Object.keys(state.touched).forEach((field) => {
    state.touched[field] = true;
  });

  // 验证所有字段
  if (!validateAllFields()) {
    Object.keys(state.errors).forEach((field) => {
      renderFieldError(field);
    });
    return;
  }

  // 设置提交状态
  state.isSubmitting = true;
  updateSubmitButton();

  try {
    // 调用注册 API
    const response = await fetch("/api/auth/register", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        username: state.formData.username,
        email: state.formData.email,
        password: state.formData.password,
      }),
    });

    const data = await response.json();

    if (!response.ok) {
      // 处理错误响应
      throw new Error(data.detail || "注册失败，请稍后重试");
    }

    // 显示成功消息
    const successMessage = document.getElementById("successMessage");
    successMessage.style.display = "flex";

    // 3 秒后跳转到登录页（实际项目中应跳转到登录页或首页）
    setTimeout(() => {
      console.log("注册成功，用户数据：", data);
      // 实际项目中应跳转到登录页
      // window.location.href = "/login";
      alert("注册成功！\n用户名：" + data.username + "\n邮箱：" + data.email);
    }, 1000);
  } catch (error) {
    console.error("注册失败：", error);
    alert("注册失败：" + error.message);
  } finally {
    state.isSubmitting = false;
    updateSubmitButton();
  }
}

// ========== 初始化 ==========
document.addEventListener("DOMContentLoaded", () => {
  // 获取表单元素
  const form = document.getElementById("registerForm");
  const usernameInput = document.getElementById("username");
  const emailInput = document.getElementById("email");
  const passwordInput = document.getElementById("password");
  const confirmPasswordInput = document.getElementById("confirmPassword");
  const togglePasswordBtn = document.getElementById("togglePassword");
  const toggleConfirmPasswordBtn = document.getElementById(
    "toggleConfirmPassword",
  );

  // 绑定表单提交事件
  form.addEventListener("submit", handleSubmit);

  // 绑定输入框事件
  usernameInput.addEventListener("input", (e) =>
    handleInputChange("username", e.target.value),
  );
  usernameInput.addEventListener("blur", () => handleInputBlur("username"));

  emailInput.addEventListener("input", (e) =>
    handleInputChange("email", e.target.value),
  );
  emailInput.addEventListener("blur", () => handleInputBlur("email"));

  passwordInput.addEventListener("input", (e) =>
    handleInputChange("password", e.target.value),
  );
  passwordInput.addEventListener("blur", () => handleInputBlur("password"));

  confirmPasswordInput.addEventListener("input", (e) =>
    handleInputChange("confirmPassword", e.target.value),
  );
  confirmPasswordInput.addEventListener("blur", () =>
    handleInputBlur("confirmPassword"),
  );

  // 绑定密码显示/隐藏按钮
  togglePasswordBtn.addEventListener("click", () =>
    togglePasswordVisibility("password", "togglePassword"),
  );
  toggleConfirmPasswordBtn.addEventListener("click", () =>
    togglePasswordVisibility("confirmPassword", "toggleConfirmPassword"),
  );

  // 初始化按钮状态
  updateSubmitButton();
});
