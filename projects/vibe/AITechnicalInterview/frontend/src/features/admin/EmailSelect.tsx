import "./admin.css";

type Props = {
  label: string;
  value: string;
  options: string[];
  onChange: (email: string) => void;
  onRemember?: (email: string) => void;
  placeholder?: string;
};

export default function EmailSelect({
  label,
  value,
  options,
  onChange,
  onRemember,
  placeholder = "name@company.ru",
}: Props) {
  const listId = `email-list-${label.replace(/\s+/g, "-")}`;

  return (
    <div className="email-field">
      <label>{label}</label>
      {options.length > 0 && (
        <select
          className="email-select"
          value=""
          onChange={(e) => {
            const picked = e.target.value;
            if (!picked) return;
            onChange(picked);
            onRemember?.(picked);
          }}
        >
          <option value="">— Выбрать сохранённый email —</option>
          {options.map((e) => (
            <option key={e} value={e}>
              {e}
            </option>
          ))}
        </select>
      )}
      <input
        type="email"
        list={listId}
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        onBlur={() => {
          if (value.trim()) onRemember?.(value);
        }}
      />
      <datalist id={listId}>
        {options.map((e) => (
          <option key={`${listId}-${e}`} value={e} />
        ))}
      </datalist>
    </div>
  );
}
