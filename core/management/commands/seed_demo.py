from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify
from django.utils import timezone

from accounts.models import Student
from core.models import ActivityLog, LearningActivity, NewsAndEvents, Semester, Session
from course.models import Course, CourseAllocation, Program
from quiz.models import Choice, MCQuestion, Progress, Quiz
from result.models import Result, TakenCourse


@dataclass(frozen=True)
class DemoUserSpec:
    username: str
    password: str
    first_name: str
    last_name: str
    email: str
    flags: dict


class Command(BaseCommand):
    help = "Seed demo data (users, courses, quizzes, results, learning activities)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--users",
            type=int,
            default=8,
            help="Number of demo students to create (default: 8).",
        )
        parser.add_argument(
            "--password",
            type=str,
            default="demo12345",
            help="Password for all demo accounts (default: demo12345).",
        )
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete existing demo objects (usernames demo_* and related data) first.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        students_count = int(options["users"])
        password = str(options["password"])
        reset = bool(options["reset"])

        User = get_user_model()

        if reset:
            self._reset_demo(User)

        # 1) Session/Semester
        session, semester = self._ensure_academic_period()

        # 1.5) News & Events
        self._ensure_news()

        # 2) Programs/Courses
        programs, courses = self._ensure_programs_and_courses()

        # 3) Users（用户名保留英文便于登录，姓名用中文便于展示）
        admin_spec = DemoUserSpec(
            username="demo_admin",
            password=password,
            first_name="演示",
            last_name="管理员",
            email="demo_admin@example.com",
            flags={"is_staff": True, "is_superuser": True},
        )
        lecturer_spec = DemoUserSpec(
            username="demo_lecturer",
            password=password,
            first_name="张",
            last_name="老师",
            email="demo_lecturer@example.com",
            flags={"is_lecturer": True},
        )

        admin = self._ensure_user(User, admin_spec)
        lecturer = self._ensure_user(User, lecturer_spec)

        students = []
        student_names = [
            ("王", "小明"), ("李", "小红"), ("陈", "小刚"), ("刘", "小芳"),
            ("杨", "小强"), ("黄", "小丽"), ("周", "小华"), ("吴", "小军"),
        ]
        for i in range(1, students_count + 1):
            first, last = student_names[(i - 1) % len(student_names)]
            spec = DemoUserSpec(
                username=f"demo_student_{i:02d}",
                password=password,
                first_name=first,
                last_name=last,
                email=f"demo_student_{i:02d}@example.com",
                flags={"is_student": True},
            )
            u = self._ensure_user(User, spec)
            u.gender = "M" if i % 2 else "F"
            u.save(update_fields=["gender"])
            students.append(u)

        # 4) Student profiles and registrations
        student_profiles = self._ensure_student_profiles(students, programs)
        self._ensure_course_allocations(lecturer, courses, session)
        self._ensure_taken_courses(student_profiles, courses)
        self._ensure_results(student_profiles, session)

        # 5) Quizzes (1 per course) + MC questions
        self._ensure_quizzes(courses)

        # 6) LearningActivity logs for last 7 days (so dashboard chart shows)
        self._ensure_learning_activities(students, courses)

        self.stdout.write(self.style.SUCCESS("中文演示数据已生成。"))
        self.stdout.write("")
        self.stdout.write("登录账号（密码一致）：")
        self.stdout.write(f"- 管理员: {admin_spec.username} / {password}")
        self.stdout.write(f"- 讲师:   {lecturer_spec.username} / {password}")
        self.stdout.write(f"- 学生:   demo_student_01 / {password}")
        self.stdout.write("")
        self.stdout.write("建议查看页面：")
        self.stdout.write("- 管理员仪表板（含学习行为趋势图）: /dashboard/")
        self.stdout.write("- 首页新闻与活动: /")
        self.stdout.write("- 学生选课: /programs/course/registration/")
        self.stdout.write("- 学生成绩与预测GPA: /result/grade/")
        self.stdout.write("- 课程列表与测验: 进入某专业 -> 课程 -> 测验")

    def _reset_demo(self, User):
        # 删除所有演示用户（级联会清理 Student/Lecturer/TakenCourse/Result/LearningActivity 等）
        demo_users = User.objects.filter(username__startswith="demo_")
        demo_users.delete()

        # 删除演示专业（级联会删除其下课程、测验、题目等）
        Program.objects.filter(title__startswith="Demo ").delete()
        Program.objects.filter(title__startswith="演示-").delete()

        # 清空新闻与活动、活动日志，便于重新生成中文演示内容
        NewsAndEvents.objects.all().delete()
        ActivityLog.objects.all().delete()

    def _ensure_academic_period(self):
        Session.objects.update(is_current_session=False)
        Semester.objects.update(is_current_semester=False)

        session, _ = Session.objects.get_or_create(
            session="2025/2026",
            defaults={"is_current_session": True},
        )
        if not session.is_current_session:
            session.is_current_session = True
            session.save(update_fields=["is_current_session"])

        semester, _ = Semester.objects.get_or_create(
            semester="First",
            session=session,
            defaults={"is_current_semester": True},
        )
        if not semester.is_current_semester:
            semester.is_current_semester = True
            semester.save(update_fields=["is_current_semester"])

        return session, semester

    def _ensure_news(self):
        # 首页新闻与活动（中文）
        news_items = [
            ("欢迎使用学习管理分析系统", "本系统支持学生选课、成绩查询、测验、学习行为分析等功能。", "News"),
            ("系统更新：学习行为与数据可视化", "仪表板现已展示最近 7 天学习行为趋势，便于分析学习活跃度。", "News"),
            ("成绩预测功能上线", "学生成绩页面可根据历史 GPA 显示下一学期预测成绩，仅供参考。", "News"),
            ("学期选课开放通知", "请同学们在规定时间内完成选课与退课操作。", "Event"),
            ("期末考试安排", "请关注各课程期末考试时间与考场安排。", "Event"),
        ]
        for title, summary, posted_as in news_items:
            NewsAndEvents.objects.get_or_create(
                title=title,
                defaults={"summary": summary, "posted_as": posted_as},
            )
        ActivityLog.objects.create(message="已生成中文演示新闻与活动。")

    def _ensure_programs_and_courses(self):
        p1, _ = Program.objects.get_or_create(
            title="演示-计算机科学",
            defaults={"summary": "演示用计算机科学专业，用于展示课程、选课、测验与成绩功能。"},
        )
        p2, _ = Program.objects.get_or_create(
            title="演示-软件工程",
            defaults={"summary": "演示用软件工程专业，用于展示多专业与课程分配。"},
        )
        p3, _ = Program.objects.get_or_create(
            title="演示-工商管理",
            defaults={"summary": "演示用工商管理专业，用于展示跨专业选课与成绩统计。"},
        )

        try:
            from django.conf import settings
            course_level = settings.LEVEL_CHOICES[0][0]
        except Exception:
            course_level = "学士"

        courses_list = [
            ("CS101", "程序设计基础", 3, "编程入门与问题求解基础。", p1),
            ("CS102", "数据结构", 3, "数组、链表、栈、队列与树等常用数据结构。", p1),
            ("CS201", "数据库原理", 3, "关系型数据库设计与 SQL 基础。", p1),
            ("SE101", "软件工程概论", 2, "软件开发流程与团队协作。", p2),
            ("BUS101", "管理学原理", 2, "管理学基本概念与案例分析。", p3),
            ("BUS102", "市场营销", 2, "市场营销基础与推广策略。", p3),
        ]
        courses = []
        for code, title, credit, summary, program in courses_list:
            c, _ = Course.objects.get_or_create(
                code=code,
                defaults={
                    "title": title,
                    "credit": credit,
                    "summary": summary,
                    "program": program,
                    "level": course_level,
                    "year": 1,
                    "semester": "First",
                },
            )
            desired_slug = slugify(code)
            if desired_slug and c.slug != desired_slug:
                c.slug = desired_slug
                c.save(update_fields=["slug"])
            courses.append(c)

        return [p1, p2, p3], courses

    def _ensure_user(self, User, spec: DemoUserSpec):
        # IMPORTANT:
        # accounts.signals.post_save_account_receiver auto-generates username/password
        # for newly created student/lecturer users. For demo seeding we want stable
        # credentials, so we avoid setting is_student/is_lecturer on the *create* call.
        user, created = User.objects.get_or_create(
            username=spec.username,
            defaults={
                "first_name": spec.first_name,
                "last_name": spec.last_name,
                "email": spec.email,
                **{k: v for k, v in spec.flags.items() if k not in ("is_student", "is_lecturer")},
            },
        )
        # keep it idempotent
        changed_fields = []
        for k, v in {
            "first_name": spec.first_name,
            "last_name": spec.last_name,
            "email": spec.email,
            **{k: v for k, v in spec.flags.items() if k not in ("is_student", "is_lecturer")},
        }.items():
            if getattr(user, k, None) != v:
                setattr(user, k, v)
                changed_fields.append(k)

        if created or changed_fields:
            user.save(update_fields=changed_fields or None)

        user.set_password(spec.password)
        user.save(update_fields=["password"])

        # ensure role flags exist even if passed in flags
        if spec.flags.get("is_lecturer"):
            user.is_lecturer = True
        if spec.flags.get("is_student"):
            user.is_student = True
        user.save(update_fields=["is_lecturer", "is_student"])
        return user

    def _ensure_student_profiles(self, student_users, programs):
        # Pick a single "level" value aligned with course creation
        try:
            from django.conf import settings

            level_value = settings.LEVEL_CHOICES[0][0]
        except Exception:
            level_value = "学士"

        profiles = []
        for idx, u in enumerate(student_users):
            program = programs[idx % len(programs)]
            obj, _ = Student.objects.get_or_create(
                student=u,
                defaults={"level": level_value, "program": program},
            )
            if obj.level != level_value or obj.program_id != program.id:
                obj.level = level_value
                obj.program = program
                obj.save(update_fields=["level", "program"])
            profiles.append(obj)
        return profiles

    def _ensure_course_allocations(self, lecturer, courses, session):
        alloc, _ = CourseAllocation.objects.get_or_create(lecturer=lecturer)
        alloc.session = session
        alloc.save(update_fields=["session"])
        alloc.courses.set(courses)

    def _ensure_taken_courses(self, student_profiles, courses):
        # Register each student to 2-3 courses
        for sp in student_profiles:
            k = random.choice([2, 3])
            chosen = random.sample(courses, k=min(k, len(courses)))
            for c in chosen:
                tc, _ = TakenCourse.objects.get_or_create(student=sp, course=c)
                # give some scores so totals/grades show
                tc.assignment = Decimal(random.randint(10, 20))
                tc.mid_exam = Decimal(random.randint(10, 20))
                tc.quiz = Decimal(random.randint(5, 15))
                tc.attendance = Decimal(random.randint(5, 10))
                tc.final_exam = Decimal(random.randint(30, 45))
                tc.save()

    def _ensure_results(self, student_profiles, session):
        # Ensure at least two GPA points for prediction in grade_results view
        for sp in student_profiles:
            r1, _ = Result.objects.get_or_create(
                student=sp,
                semester="First",
                session=session.session,
                level=sp.level,
                defaults={"gpa": round(random.uniform(2.4, 3.6), 2), "cgpa": None},
            )
            if r1.gpa is None:
                r1.gpa = round(random.uniform(2.4, 3.6), 2)
                r1.save(update_fields=["gpa"])

            r2, _ = Result.objects.get_or_create(
                student=sp,
                semester="Second",
                session=session.session,
                level=sp.level,
                defaults={"gpa": round(min(r1.gpa + random.uniform(-0.3, 0.4), 4.0), 2), "cgpa": None},
            )
            if r2.gpa is None:
                r2.gpa = round(min((r1.gpa or 3.0) + random.uniform(-0.3, 0.4), 4.0), 2)
                r2.save(update_fields=["gpa"])

    def _ensure_quizzes(self, courses):
        """
        为每门课程生成多个中文测验与更多题目，便于学生端直接看到“测验系统”的完整展示。
        """

        quiz_bank = {
            "CS101": [
                (
                    "程序设计基础 - 章节测验A",
                    "变量、函数与基础语法。",
                    [
                        ("以下哪一种是合法的变量名？", ["2ab", "ab2", "break", "a-b"], 1),
                        ("Python 中定义函数使用哪个关键字？", ["function", "def", "func", "define"], 1),
                        ("下列哪项表示字符串拼接？", ["+", "*", "-", "/"], 0),
                        ("for 循环常用于？", ["条件判断", "重复执行", "异常处理", "定义类"], 1),
                    ],
                ),
                (
                    "程序设计基础 - 章节测验B",
                    "条件、列表与常见错误。",
                    [
                        ("下列哪项会导致语法错误？", ["if x:", "if (x):", "if x", "if x == 1:"], 2),
                        ("列表下标从几开始？", ["0", "1", "-1", "不确定"], 0),
                        ("len([1,2,3]) 的结果是？", ["2", "3", "4", "报错"], 1),
                        ("异常处理常用关键字是？", ["try/except", "catch/throw", "guard", "safe"], 0),
                    ],
                ),
            ],
            "CS102": [
                (
                    "数据结构 - 章节测验A",
                    "线性结构与基本概念。",
                    [
                        ("栈的特点是？", ["先进先出", "先进后出", "随机存取", "无序"], 1),
                        ("队列的特点是？", ["先进先出", "先进后出", "随机存取", "无序"], 0),
                        ("下列哪项不是线性结构？", ["数组", "链表", "栈", "树"], 3),
                        ("链表相比数组的优势常见是？", ["随机访问快", "插入删除更灵活", "占用更少内存", "一定更快"], 1),
                    ],
                ),
                (
                    "数据结构 - 章节测验B",
                    "树与复杂度。",
                    [
                        ("二叉树每个节点最多有几个子节点？", ["1", "2", "3", "无限"], 1),
                        ("时间复杂度 \(O(n)\) 表示？", ["常数时间", "线性增长", "对数增长", "平方增长"], 1),
                        ("下列哪种遍历属于深度优先？", ["层序遍历", "前序遍历", "广度优先", "以上都不是"], 1),
                        ("哈希表主要用于？", ["排序", "快速查找", "图遍历", "压缩"], 1),
                    ],
                ),
            ],
            "CS201": [
                (
                    "数据库原理 - 测验A",
                    "SQL 与基础概念。",
                    [
                        ("SQL 中查询数据使用哪个关键字？", ["GET", "SELECT", "FETCH", "QUERY"], 1),
                        ("主键的作用是？", ["加快查询", "唯一标识一行", "排序", "分组"], 1),
                        ("WHERE 子句用于？", ["排序", "过滤", "分组", "连接"], 1),
                        ("JOIN 主要用于？", ["删除表", "连接多表查询", "创建索引", "备份数据"], 1),
                    ],
                ),
                (
                    "数据库原理 - 测验B",
                    "范式与索引。",
                    [
                        ("范式的目标主要是？", ["增加冗余", "减少冗余与异常", "让 SQL 更长", "提高 UI 体验"], 1),
                        ("索引通常可以？", ["降低查询性能", "提高查询速度", "删除数据", "替代主键"], 1),
                        ("事务的 ACID 中 C 表示？", ["一致性", "并发性", "压缩性", "缓存"], 0),
                        ("外键主要用于？", ["保证引用完整性", "加密字段", "压缩数据", "生成报表"], 0),
                    ],
                ),
            ],
        }

        default_quizzes = [
            (
                "课程综合测验A",
                "综合演示测验（A）。",
                [
                    ("以下哪项描述最合理？", ["选项A", "选项B", "选项C", "选项D"], 1),
                    ("系统的主要目的之一是？", ["数据分析", "绘图", "登录", "以上都是"], 3),
                    ("完成测验后可以？", ["查看结果", "无法查看", "只能管理员查看", "只能讲师查看"], 0),
                    ("学习行为追踪能帮助？", ["统计活跃度", "分析学习路径", "优化教学", "以上都是"], 3),
                ],
            ),
            (
                "课程综合测验B",
                "综合演示测验（B）。",
                [
                    ("下列哪个属于系统功能？", ["选课", "成绩管理", "测验", "以上都是"], 3),
                    ("学生可以在系统中？", ["查看成绩", "参与测验", "浏览课程", "以上都是"], 3),
                    ("管理员可以在仪表板看到？", ["统计图表", "活动日志", "用户数量", "以上都是"], 3),
                    ("预测 GPA 属于？", ["分析功能", "支付功能", "上传功能", "无关功能"], 0),
                ],
            ),
        ]

        def ensure_quiz(course, title, desc, questions_data):
            quiz, _ = Quiz.objects.get_or_create(
                course=course,
                title=title,
                defaults={
                    "description": desc,
                    "category": "practice",
                    "random_order": True,
                    "answers_at_end": True,
                    "exam_paper": True,
                    "single_attempt": False,
                    "pass_mark": 50,
                    "draft": False,
                },
            )
            for content, choices_texts, correct_idx in questions_data:
                if MCQuestion.objects.filter(quiz=quiz, content=content).exists():
                    continue
                q = MCQuestion.objects.create(
                    content=content,
                    explanation="本题为演示题目，解析略。",
                    choice_order="random",
                )
                q.quiz.add(quiz)
                for i, choice_text in enumerate(choices_texts):
                    Choice.objects.create(
                        question=q,
                        choice_text=choice_text,
                        correct=(i == correct_idx),
                    )

        for course in courses:
            quizzes = quiz_bank.get(course.code, None)
            if quizzes is None:
                quizzes = [
                    (f"{course.title} - {t}", d, q) for (t, d, q) in default_quizzes
                ]
            for title, desc, questions_data in quizzes:
                ensure_quiz(course, title, desc, questions_data)

    def _ensure_learning_activities(self, student_users, courses):
        now = timezone.now()
        desc_map = {
            LearningActivity.ACTIVITY_VIEW_COURSE: "浏览课程",
            LearningActivity.ACTIVITY_TAKE_QUIZ: "参与测验",
            LearningActivity.ACTIVITY_FINISH_QUIZ: "完成测验",
            LearningActivity.ACTIVITY_VIEW_RESULT: "查看成绩",
            LearningActivity.ACTIVITY_COURSE_REGISTER: "选课/退课",
        }
        for day_offset in range(0, 7):
            dt = now - timedelta(days=day_offset)
            per_day = random.randint(8, 25)
            for _ in range(per_day):
                user = random.choice(student_users)
                course = random.choice(courses)
                act = random.choice(
                    [
                        LearningActivity.ACTIVITY_VIEW_COURSE,
                        LearningActivity.ACTIVITY_TAKE_QUIZ,
                        LearningActivity.ACTIVITY_FINISH_QUIZ,
                        LearningActivity.ACTIVITY_VIEW_RESULT,
                        LearningActivity.ACTIVITY_COURSE_REGISTER,
                    ]
                )
                LearningActivity.objects.create(
                    user=user,
                    student=Student.objects.filter(student=user).first(),
                    course=course,
                    activity_type=act,
                    description=desc_map.get(act, "演示学习行为"),
                    created_at=dt,
                )
        for u in student_users:
            Progress.objects.get_or_create(user=u, defaults={"score": ""})

