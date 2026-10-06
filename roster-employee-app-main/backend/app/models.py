from datetime import date, datetime, timezone
from typing import List, Optional

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Region(SQLModel, table=True):
    id: str = Field(primary_key=True)
    name: str
    code: str
    country: str
    timezone: str  # IANA timezone, e.g. "Africa/Lagos"
    lead_id: Optional[str] = Field(default=None, foreign_key="employee.id")

    # Lifecycle metadata for soft-delete and restore visibility.
    deleted_at: Optional[datetime] = Field(default=None)
    deleted_by_id: Optional[str] = Field(default=None, foreign_key="employee.id")
    deleted_reason: Optional[str] = Field(default=None)


class RegionCreate(SQLModel):
    name: str
    code: str
    country: str
    timezone: str
    lead_id: Optional[str] = None


class RegionUpdate(SQLModel):
    name: Optional[str] = None
    code: Optional[str] = None
    country: Optional[str] = None
    timezone: Optional[str] = None
    lead_id: Optional[str] = None


class Employee(SQLModel, table=True):
    id: str = Field(primary_key=True)
    name: str
    email: str
    role: str  # job title, e.g. "Backend Engineer"
    access_role: str = Field(default="employee")  # RBAC role; lead is assigned only through a region
    password_hash: str = Field(default="")
    is_suspended: bool = Field(default=False)  # suspended accounts can't log in
    assignment: str  # free-text current focus, kept for quick display
    region_id: str = Field(foreign_key="region.id")
    status: str = Field(default="active")  # active | deployed | on_leave | offline
    stack: List[str] = Field(default_factory=list, sa_column=Column(JSON))
    joined_date: date

    # Lifecycle metadata for soft-delete and restore visibility.
    deleted_at: Optional[datetime] = Field(default=None)
    deleted_by_id: Optional[str] = Field(default=None, foreign_key="employee.id")
    deleted_reason: Optional[str] = Field(default=None)


class EmployeePublic(SQLModel):
    """What the API actually returns for an employee - never password_hash."""

    id: str
    name: str
    email: str
    role: str
    access_role: str
    is_suspended: bool
    assignment: str
    region_id: str
    status: str
    stack: List[str]
    joined_date: date


class EmployeeMe(EmployeePublic):
    """Authenticated employee payload with the display-ready region name."""

    region_name: Optional[str] = None


class EmployeeCreate(SQLModel):
    """Account creation is admin-only - there is no public self-registration."""

    name: str
    email: str
    role: str
    access_role: str = "employee"  # lead is assigned only via a region
    region_id: str
    assignment: str = ""
    stack: List[str] = []
    status: str = "active"
    password: str


class EmployeeUpdate(SQLModel):
    name: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None
    access_role: Optional[str] = None  # admin/super_admin only - enforced in the router
    region_id: Optional[str] = None
    status: Optional[str] = None
    assignment: Optional[str] = None
    stack: Optional[List[str]] = None


class PasswordChange(SQLModel):
    current_password: str
    new_password: str


class Project(SQLModel, table=True):
    id: str = Field(primary_key=True)
    name: str
    description: str
    client: Optional[str] = None
    status: str = Field(default="active")  # active | on_hold | completed
    member_ids: List[str] = Field(default_factory=list, sa_column=Column(JSON))
    links: List[dict] = Field(default_factory=list, sa_column=Column(JSON))  # [{"title": str, "url": str, "category": Optional[str]}]
    start_date: Optional[date] = Field(default=None)
    deadline: Optional[date] = Field(default=None)
    created_at: date = Field(default_factory=date.today)
    creator_id: str = Field(foreign_key="employee.id")

    # Lifecycle metadata used for soft-delete, archive, restore, and audit 
    deleted_at: Optional[datetime] = Field(default=None)
    deleted_by_id: Optional[str] = Field(default=None, foreign_key="employee.id")
    deleted_reason: Optional[str] = Field(default=None)
    archived_at: Optional[datetime] = Field(default=None)
    archived_by_id: Optional[str] = Field(default=None, foreign_key="employee.id")


class ProjectCreate(SQLModel):
    name: str
    description: str
    client: Optional[str] = None
    member_ids: List[str] = []
    links: List[dict] = []
    start_date: Optional[date] = None
    deadline: Optional[date] = None


class ProjectUpdate(SQLModel):
    name: Optional[str] = None
    description: Optional[str] = None
    client: Optional[str] = None
    status: Optional[str] = None
    member_ids: Optional[List[str]] = None
    links: Optional[List[dict]] = None
    start_date: Optional[date] = None
    deadline: Optional[date] = None


class Milestone(SQLModel, table=True):
    id: str = Field(primary_key=True)
    project_id: str = Field(foreign_key="project.id", index=True)
    title: str
    description: Optional[str] = None
    due_date: Optional[date] = None
    status: str = Field(default="pending")  # pending | in_progress | completed
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class MilestoneCreate(SQLModel):
    project_id: str
    title: str
    description: Optional[str] = None
    due_date: Optional[date] = None
    status: str = "pending"


class MilestoneUpdate(SQLModel):
    title: Optional[str] = None
    description: Optional[str] = None
    due_date: Optional[date] = None
    status: Optional[str] = None


class SubTask(SQLModel):
    title: str
    completed: bool = False


class Task(SQLModel, table=True):
    id: str = Field(primary_key=True)
    project_id: str = Field(foreign_key="project.id")
    milestone_id: Optional[str] = Field(default=None, foreign_key="milestone.id")
    title: str
    description: str = ""
    subtasks: List[dict] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )
    status: str = Field(default="todo")  # todo | in_progress | in_review | completed
    priority: str = Field(default="medium")  # low | medium | high | urgent
    assignee_id: Optional[str] = Field(default=None, foreign_key="employee.id")
    due_date: Optional[date] = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    # Lifecycle metadata used for soft-delete and trash visibility.
    deleted_at: Optional[datetime] = Field(default=None)
    deleted_by_id: Optional[str] = Field(default=None, foreign_key="employee.id")
    deleted_reason: Optional[str] = Field(default=None)


class TaskCreate(SQLModel):
    project_id: str
    milestone_id: Optional[str] = None
    title: str
    description: str = ""
    subtasks: List[SubTask] = Field(default_factory=list)
    status: str = "todo"
    priority: str = "medium"
    assignee_id: Optional[str] = None
    due_date: Optional[date] = None


class TaskUpdate(SQLModel):
    title: Optional[str] = None
    description: Optional[str] = None
    subtasks: Optional[List[SubTask]] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    assignee_id: Optional[str] = None
    due_date: Optional[date] = None
    project_id: Optional[str] = None
    milestone_id: Optional[str] = None


class Post(SQLModel, table=True):
    """A lightweight social post/snippet an employee shares - the community feed."""

    id: str = Field(primary_key=True)
    author_id: str = Field(foreign_key="employee.id")
    content: str
    link_url: Optional[str] = None
    image_url: Optional[str] = None  # http(s) URL or a data: URI for an uploaded image
    tags: List[str] = Field(default_factory=list, sa_column=Column(JSON))
    liked_by: List[str] = Field(default_factory=list, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utc_now)

    # Lifecycle metadata for a community-post soft delete and restore flow.
    deleted_at: Optional[datetime] = Field(default=None)
    deleted_by_id: Optional[str] = Field(default=None, foreign_key="employee.id")
    deleted_reason: Optional[str] = Field(default=None)


class PostCreate(SQLModel):
    content: str
    link_url: Optional[str] = None
    image_url: Optional[str] = None
    tags: List[str] = []


class ChatChannel(SQLModel, table=True):
    """
    kind determines how access is computed (see app/chat_access.py):
      - "general": everyone.
      - "region": admins/super admins see every region channel; everyone
        else only sees the one matching their own region_id.
      - "project": auto-created alongside each project. Admins/super
        admins see every project's channel; everyone else only sees it if
        they're a member of that project.
      - "custom": admin-created, scoped by region_scope + role_scope.
        An empty list means "all" for that dimension.
      - "direct": a 1:1 DM - visible only to the two ids in member_ids.
    """

    id: str = Field(primary_key=True)
    name: str
    kind: str = Field(default="general")
    region_id: Optional[str] = None  # set when kind == "region"
    project_id: Optional[str] = Field(default=None, foreign_key="project.id")  # kind == "project"
    region_scope: List[str] = Field(default_factory=list, sa_column=Column(JSON))  # kind == "custom"
    role_scope: List[str] = Field(default_factory=list, sa_column=Column(JSON))  # kind == "custom"
    member_ids: List[str] = Field(default_factory=list, sa_column=Column(JSON))  # kind == "direct"
    created_by: Optional[str] = Field(default=None, foreign_key="employee.id")
    created_at: datetime = Field(default_factory=utc_now)

    # Chat lifecycle metadata used when a project discussion is archived,
    # hidden because the parent project was deleted, or restored.
    deleted_at: Optional[datetime] = Field(default=None)
    deleted_by_id: Optional[str] = Field(default=None, foreign_key="employee.id")
    archived_at: Optional[datetime] = Field(default=None)
    archived_by_id: Optional[str] = Field(default=None, foreign_key="employee.id")


class ChannelCreate(SQLModel):
    name: str
    region_scope: List[str] = []  # [] == all regions
    role_scope: List[str] = []  # [] == all roles


class DirectChannelCreate(SQLModel):
    employee_id: str  # the other participant


class ChatMessage(SQLModel, table=True):
    id: str = Field(primary_key=True)
    channel_id: str = Field(foreign_key="chatchannel.id")
    sender_id: str = Field(foreign_key="employee.id")
    content: str
    sent_at: datetime = Field(default_factory=utc_now)


class MessageCreate(SQLModel):
    sender_id: str
    content: str


class LoginRequest(SQLModel):
    email: str
    password: str


class LoginResponse(SQLModel):
    token: str
    user: EmployeePublic


class DeletedContentItem(SQLModel):
    """Normalized deleted-resource payload for the cross-resource trash feed."""

    category: str
    resource_type: str
    id: str
    name: Optional[str] = None
    deleted_at: Optional[datetime] = None
    deleted_by_id: Optional[str] = None
    deleted_reason: Optional[str] = None


class AuthSession(SQLModel, table=True):
    """Bearer session tokens, persisted in the DB rather than kept in a
    process-local dict. This matters as soon as the backend runs more than
    one worker process (or gets restarted/recycled between requests, which
    a lot of hosts do) - an in-memory dict is invisible across processes,
    so a token issued by worker A would 401 on worker B. All workers share
    this same SQLite file, so this store doesn't have that problem."""

    token: str = Field(primary_key=True)
    employee_id: str = Field(foreign_key="employee.id")
    created_at: datetime = Field(default_factory=utc_now)


# ─────────────────────────────────────────────
# Notifications
# ─────────────────────────────────────────────


class Notification(SQLModel, table=True):
    id: str = Field(primary_key=True)
    recipient_id: str = Field(foreign_key="employee.id")
    type: str  # task.assigned | task.status_changed | project.added | chat.direct_message
    message: str
    link: Optional[str] = None  # a frontend route, e.g. "/tasks" or "/projects/proj-atlas"
    read: bool = Field(default=False)
    created_at: datetime = Field(default_factory=utc_now)


# ─────────────────────────────────────────────
# Audit log
# ─────────────────────────────────────────────


class AuditLog(SQLModel, table=True):
    id: str = Field(primary_key=True)
    actor_id: str = Field(foreign_key="employee.id")
    action: str  # e.g. "employee.suspended", "task.deleted", "project.created"
    target_type: str  # "employee" | "region" | "project" | "task" | "chat_channel"
    target_id: str
    detail: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now)


# ─────────────────────────────────────────────
# Support tickets
# ─────────────────────────────────────────────


class SupportTicket(SQLModel, table=True):
    id: str = Field(primary_key=True)
    requester_id: str = Field(foreign_key="employee.id")
    subject: str
    status: str = Field(default="open")  # open | in_progress | resolved | closed
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    # Lifecycle metadata for ticket soft-delete and restore visibility.
    deleted_at: Optional[datetime] = Field(default=None)
    deleted_by_id: Optional[str] = Field(default=None, foreign_key="employee.id")
    deleted_reason: Optional[str] = Field(default=None)


class SupportTicketCreate(SQLModel):
    subject: str
    message: str
    attachment_url: Optional[str] = None


class SupportTicketUpdate(SQLModel):
    status: Optional[str] = None


class SupportMessage(SQLModel, table=True):
    id: str = Field(primary_key=True)
    ticket_id: str = Field(foreign_key="supportticket.id")
    sender_id: str = Field(foreign_key="employee.id")
    content: str
    attachment_url: Optional[str] = None  # data: URI or http(s) URL, same pattern as posts
    created_at: datetime = Field(default_factory=utc_now)


class SupportMessageCreate(SQLModel):
    content: str
    attachment_url: Optional[str] = None
