"use client";

import { useState, type InputHTMLAttributes } from "react";
import { useI18n } from "@/lib/i18n";

type Props = Omit<InputHTMLAttributes<HTMLInputElement>, "type"> & {
  name: string;
};

export function PasswordField(props: Props) {
  const { t } = useI18n();
  const [visible, setVisible] = useState(false);
  const { className, ...rest } = props;

  return (
    <div className={`password-field${className ? ` ${className}` : ""}`}>
      <input {...rest} type={visible ? "text" : "password"} />
      <button
        type="button"
        className="password-toggle"
        onClick={() => setVisible((v) => !v)}
        aria-label={visible ? t("auth.hide_password") : t("auth.show_password")}
        title={visible ? t("auth.hide_password") : t("auth.show_password")}
      >
        {visible ? t("auth.hide_password") : t("auth.show_password")}
      </button>
    </div>
  );
}
