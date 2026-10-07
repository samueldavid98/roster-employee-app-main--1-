import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from sqlalchemy import cast, or_
from sqlalchemy.dialects.postgresql import JSONB

from .system.audit import log_action
from .system.auth import get_current_employee
from ..database import get_session
from ..models import Employee, Project, Task, TaskCreate, TaskUpdate
from .system.notifications import notify
from ..permissions import Permission, Role, has_permission, require_permission, role_of

router = APIRouter(prefix="/api/tasks", tags=["tasks"])

# An employee can move their own task through the working states, but the
# final sign-off is a manager call - not something they grant themselves.
EMPLOYEE_ALLOWED_STATUSES = {"todo", "in_progress", "in_review"}


@router.get("", response_model=List[Task])
def list_tasks(
    status: Optional[str] = None,
    priority: Optional[str] = None,
    project_id: Optional[str] = None,
    assignee_id: Optional[str] = None,
    session: Session = Depends(get_session),
    current: Employee = Depends(require_permission(Permission.TASKS_VIEW)),
):
    is_employee = not has_permission(role_of(current), Permission.PROJECTS_EDIT_FULL_ACCESS)
    is_manager = has_permission(role_of(current), Permission.PROJECTS_EXTEND_VIEW)
    is_admin = has_permission(role_of(current), Permission.PROJECTS_FULL_ACCESS)

    if project_id:
        project = session.get(Project, project_id)
        if not project:
            raise HTTPException(status_code=403, detail="Project doesn't exist")

        if is_employee:
            if is_manager:
                if current.id != project.creator_id and current.id not in project.member_ids:
                    raise HTTPException(status_code=403, detail="You're not on this project")
            else:
                if current.id not in project.member_ids:
                    raise HTTPException(status_code=403, detail="You're not on this project")

    query = select(Task)
    if not is_admin:
        query = query.where(Task.deleted_at.is_(None))
    if status:
        query = query.where(Task.status == status)
    if priority:
        query = query.where(Task.priority == priority)
    if project_id:
        query = query.where(Task.project_id == project_id)
    if assignee_id:
        query = query.where(Task.assignee_id == assignee_id)

    if not project_id and is_employee:
        if is_manager:
            allowed_projects = select(Project.id).where(
                or_(
                    Project.creator_id == current.id,
                    cast(Project.member_ids, JSONB).contains([current.id]),
                )
            )
            query = query.where(
                        or_(
                            Task.project_id.in_(allowed_projects),
                            Task.assignee_id == current.id,
                        )
                    )
        else:
            allowed_projects = select(Project.id).where(
                cast(Project.member_ids, JSONB).contains([current.id])
            )
            query = query.where(Task.assignee_id == current.id)
            
    tasks = session.exec(query).all()

    return sorted(tasks, key=lambda t: t.created_at, reverse=True)


@router.post("", response_model=Task, status_code=201)
def create_task(
    payload: TaskCreate,
    session: Session = Depends(get_session),
    current: Employee = Depends(require_permission(Permission.TASKS_CREATE)),
):
    project = session.get(Project, payload.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Super Admin project protection rule:
    creator = session.get(Employee, project.creator_id)
    if (
        creator and creator.access_role == Role.SUPER_ADMIN.value
        and role_of(current) == Role.ADMIN
        and current.id not in project.member_ids
    ):
        raise HTTPException(
            status_code=403,
            detail="An Admin cannot add tasks to a Super Admin's project unless added as a member."
        )

    task = Task(id=str(uuid.uuid4()), **payload.model_dump())
    session.add(task)
    session.commit()
    session.refresh(task)

    # Auto-add non-member assignee to project so they have full visibility and access
    if task.assignee_id and task.assignee_id not in project.member_ids:
        project.member_ids = list(project.member_ids) + [task.assignee_id]
        session.add(project)
        session.commit()
        session.refresh(project)
        notify(task.assignee_id, "project.added", f"You were added to {project.name}", link=f"/projects/{project.id}")

    if task.assignee_id and task.assignee_id != current.id:
        notify(task.assignee_id, "task.assigned", f"You were assigned: {task.title}", link=f"/tasks?taskId={task.id}")

    log_action(current.id, "task.created", "task", task.id, detail=task.title)
    return task


@router.patch("/{task_id}", response_model=Task)
def update_task(
    task_id: str,
    payload: TaskUpdate,
    session: Session = Depends(get_session),
    current: Employee = Depends(get_current_employee),
):
    task = session.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    project = session.get(Project, task.project_id)
    if project:
        # Super Admin project protection rule:
        creator = session.get(Employee, project.creator_id)
        if (
            creator and creator.access_role == Role.SUPER_ADMIN.value
            and role_of(current) == Role.ADMIN
            and current.id not in project.member_ids
        ):
            raise HTTPException(
                status_code=403,
                detail="An Admin cannot edit tasks on a Super Admin's project unless added as a member."
            )

    if not has_permission(role_of(current), Permission.TASKS_EDIT):
        raise HTTPException(status_code=403, detail="Not permitted to edit tasks")

    updates = payload.model_dump(exclude_unset=True)
    role = role_of(current)

    # Regular employee or assignee status-only restriction:
    if not has_permission(role, Permission.TASKS_MANAGE) or task.assignee_id == current.id:
        if task.assignee_id != current.id and not has_permission(role, Permission.TASKS_MANAGE):
            raise HTTPException(status_code=403, detail="You can only update tasks assigned to you")
        disallowed = set(updates) - {"status"}
        if disallowed and not has_permission(role, Permission.TASKS_MANAGE):
            raise HTTPException(
                status_code=403,
                detail="You can only update a task's status - priority, assignee, and due date are set by your manager.",
            )
        if updates.get("status") not in (None, *EMPLOYEE_ALLOWED_STATUSES) and not has_permission(role, Permission.TASKS_MANAGE):
            raise HTTPException(
                status_code=403,
                detail="Only a manager or admin can mark a task completed - move it to 'In review' instead.",
            )

    previous_assignee = task.assignee_id
    for field, value in updates.items():
        setattr(task, field, value)
    task.updated_at = datetime.utcnow()
    session.add(task)
    session.commit()
    session.refresh(task)

    # If new assignee is not in the project, add them automatically
    if project and task.assignee_id and task.assignee_id not in project.member_ids:
        project.member_ids = list(project.member_ids) + [task.assignee_id]
        session.add(project)
        session.commit()
        session.refresh(project)
        notify(task.assignee_id, "project.added", f"You were added to {project.name}", link=f"/projects/{project.id}")

    if "assignee_id" in updates and task.assignee_id and task.assignee_id != previous_assignee and task.assignee_id != current.id:
        notify(task.assignee_id, "task.assigned", f"You were assigned: {task.title}", link=f"/tasks?taskId={task.id}")
    elif "status" in updates and task.assignee_id and task.assignee_id != current.id:
        notify(task.assignee_id, "task.status_changed", f"{current.name} moved '{task.title}' to {task.status}", link=f"/tasks?taskId={task.id}")

    log_action(current.id, "task.updated", "task", task.id, detail=", ".join(updates.keys()))
    return task


@router.post("/{task_id}/restore", response_model=Task)
def restore_task(
    task_id: str,
    session: Session = Depends(get_session),
    current: Employee = Depends(require_permission(Permission.TASKS_DELETE)),
):
    task = session.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    task.deleted_at = None
    task.deleted_by_id = None
    task.deleted_reason = None
    session.add(task)
    session.commit()
    session.refresh(task)

    log_action(current.id, "task.restored", "task", task.id, detail=task.title)
    return task


@router.delete("/{task_id}", status_code=204)
def delete_task(
    task_id: str,
    session: Session = Depends(get_session),
    current: Employee = Depends(require_permission(Permission.TASKS_DELETE)),
):
    task = session.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    task.deleted_at = datetime.utcnow()
    task.deleted_by_id = current.id
    task.deleted_reason = "soft-delete"
    task.status = "completed"
    session.add(task)
    session.commit()

    log_action(current.id, "task.deleted", "task", task.id, detail=task.title)
    return None
