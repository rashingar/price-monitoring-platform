import { Link } from "react-router-dom";
import {
  platformHealthStatusClass,
  platformHealthStatusLabel,
} from "./platformHealthFormatters";
import type { PlatformHealthGroup } from "./platformHealthTypes";

interface PlatformHealthGroupCardProps {
  group: PlatformHealthGroup;
}

export function PlatformHealthGroupCard({ group }: PlatformHealthGroupCardProps) {
  const hasBlockingReasons = group.blocking_reasons.length > 0;
  const hasWarnings = group.warnings.length > 0;
  const hasDetails = group.details.length > 0;
  const hasLinks = group.links.length > 0;

  return (
    <article className={`platform-health-card platform-health-card-${group.status}`}>
      <div className="platform-health-card-heading">
        <div>
          <h4>{group.label}</h4>
          <p>{group.summary}</p>
        </div>
        <span className={`status-badge ${platformHealthStatusClass(group.status)}`}>
          {platformHealthStatusLabel(group.status)}
        </span>
      </div>

      {hasBlockingReasons ? (
        <div className="platform-health-message danger">
          <strong>Blocking reasons</strong>
          <ul>
            {group.blocking_reasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {hasWarnings ? (
        <div className="platform-health-message warning">
          <strong>Warnings</strong>
          <ul>
            {group.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {hasDetails ? (
        <div className="platform-health-message">
          <strong>Details</strong>
          <ul>
            {group.details.map((detail) => (
              <li key={detail}>{detail}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {hasLinks ? (
        <div className="platform-health-links" aria-label={`${group.label} links`}>
          {group.links.map((link) => (
            <Link key={`${group.id}-${link.url}-${link.label}`} to={link.url}>
              {link.label}
            </Link>
          ))}
        </div>
      ) : null}
    </article>
  );
}
