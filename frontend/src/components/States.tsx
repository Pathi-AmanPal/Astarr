/** Designed loading / error / empty / not-found states.
    PRD Section 7: no screen may ever render a blank area or an unhandled error. */

import { Link } from "react-router-dom";

export function Loading({ rows = 6, label }: { rows?: number; label: string }) {
  return (
    <div className="skeleton" role="status" aria-live="polite">
      <span className="sr-only">{label}</span>
      {Array.from({ length: rows }, (_, i) => (
        <div className="skeleton__row" key={i} aria-hidden="true" />
      ))}
    </div>
  );
}

export function ErrorState({
  title = "Could not load this view",
  message,
  onRetry,
  backTo,
}: {
  title?: string;
  message: string;
  onRetry?: () => void;
  backTo?: boolean;
}) {
  return (
    <div className="state state--error" role="alert">
      <p className="state__title">{title}</p>
      <p className="state__body">{message}</p>
      <div className="state__actions">
        {onRetry && (
          <button type="button" className="btn" onClick={onRetry}>
            Try again
          </button>
        )}
        {backTo && (
          <>
            {onRetry ? " " : null}
            <Link className="crumb" to="/">
              Back to all entities
            </Link>
          </>
        )}
      </div>
    </div>
  );
}

export function NotFound({ message }: { message: string }) {
  return (
    <div className="state" role="alert">
      <p className="state__title">{message}</p>
      <p className="state__body">
        It may have been removed by a demo reset. The entity list is always current.
      </p>
      <div className="state__actions">
        <Link className="crumb" to="/">
          Back to all entities
        </Link>
      </div>
    </div>
  );
}

export function Empty({ children }: { children: React.ReactNode }) {
  return <p className="empty">{children}</p>;
}
