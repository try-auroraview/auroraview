import { cn } from '../lib/utils';
import * as Icons from 'lucide-react';

interface QuickLinkProps {
  href?: string;
  onClick?: () => void;
  icon: React.ReactNode;
  iconGradient: string;
  title: string;
  description: string;
  external?: boolean;
}

function QuickLink({ href, onClick, icon, iconGradient, title, description, external }: QuickLinkProps) {
  const handleClick = (e: React.MouseEvent) => {
    if (onClick) {
      e.preventDefault();
      onClick();
    }
  };

  return (
    <a
      href={href || '#'}
      onClick={handleClick}
      className={cn(
        "bg-card border border-border rounded-xl p-5 no-underline text-foreground",
        "card-shadow gradient-border",
        "transition-all flex flex-col gap-3 cursor-pointer group",
        "hover:border-primary/40"
      )}
      target={external ? "_blank" : undefined}
      rel={external ? "noopener noreferrer" : undefined}
    >
      <div className={cn(
        "w-12 h-12 rounded-xl flex items-center justify-center",
        "bg-gradient-to-br shadow-lg",
        iconGradient
      )}>
        {icon}
      </div>
      <div>
        <div className="font-semibold text-sm flex items-center gap-1.5 group-hover:text-primary transition-colors">
          {title}
          {external && <Icons.ExternalLink className="w-3 h-3 text-muted-foreground" />}
        </div>
        <div className="text-xs text-muted-foreground mt-1.5 leading-relaxed">{description}</div>
      </div>
    </a>
  );
}

interface QuickLinksProps {
  onCategoryClick: (categoryId: string) => void;
  onOpenLink: (url: string, title?: string) => void;
}

export function QuickLinks({ onCategoryClick, onOpenLink }: QuickLinksProps) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-12">
      <QuickLink
        onClick={() => onCategoryClick('getting_started')}
        icon={<Icons.Sparkles className="w-6 h-6 text-white" />}
        iconGradient="from-violet-500 to-purple-600"
        title="Getting Started"
        description="An overview of app development options and samples."
      />
      <QuickLink
        onClick={() => onOpenLink('https://github.com/try-auroraview/auroraview', 'GitHub - AuroraView')}
        icon={<Icons.Github className="w-6 h-6 text-white" />}
        iconGradient="from-gray-600 to-gray-800"
        title="GitHub Repo"
        description="The latest design controls and styles for your applications."
        external
      />
      <QuickLink
        onClick={() => onCategoryClick('api_patterns')}
        icon={<Icons.Braces className="w-6 h-6 text-white" />}
        iconGradient="from-orange-500 to-amber-500"
        title="Code Samples"
        description="Find samples that demonstrate specific tasks, features and APIs."
      />
      <QuickLink
        onClick={() => onOpenLink('https://github.com/try-auroraview/auroraview/issues', 'GitHub Issues - AuroraView')}
        icon={<Icons.MessageSquare className="w-6 h-6 text-white" />}
        iconGradient="from-emerald-500 to-green-600"
        title="Send Feedback"
        description="Help us improve AuroraView by providing feedback."
        external
      />
    </div>
  );
}
