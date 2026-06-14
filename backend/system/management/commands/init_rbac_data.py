"""
初始化 RBAC 权限数据
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from system.models import Menu, Role, SystemUserProfile


class Command(BaseCommand):
    help = '初始化 RBAC 权限数据'

    def handle(self, *args, **options):
        self.stdout.write('开始初始化 RBAC 数据...')

        # 1. 创建菜单和权限
        menus = self.create_menus()

        # 2. 创建角色
        admin_role = self.create_roles(menus)

        # 3. 为管理员用户分配角色
        self.assign_admin_role(admin_role)

        self.stdout.write(self.style.SUCCESS('RBAC 数据初始化完成！'))

    def create_menus(self):
        """创建菜单和权限"""
        self.stdout.write('创建菜单...')

        # 系统管理目录
        system_dir, _ = Menu.objects.get_or_create(
            name='系统管理',
            defaults={
                'code': 'sys:manage',
                'path': '/system',
                'type': 'directory',
                'icon': 'Setting',
                'order': 100,
            }
        )

        # 菜单管理
        menu_menu, _ = Menu.objects.get_or_create(
            name='菜单管理',
            defaults={
                'code': 'sys:menu:list',
                'path': '/system/menu',
                'type': 'menu',
                'icon': 'Menu',
                'parent': system_dir,
                'order': 1,
            }
        )

        # 菜单权限按钮
        Menu.objects.get_or_create(
            name='菜单新增',
            defaults={
                'code': 'sys:menu:add',
                'type': 'button',
                'parent': menu_menu,
                'order': 1,
            }
        )
        Menu.objects.get_or_create(
            name='菜单编辑',
            defaults={
                'code': 'sys:menu:edit',
                'type': 'button',
                'parent': menu_menu,
                'order': 2,
            }
        )
        Menu.objects.get_or_create(
            name='菜单删除',
            defaults={
                'code': 'sys:menu:delete',
                'type': 'button',
                'parent': menu_menu,
                'order': 3,
            }
        )

        # 角色管理
        role_menu, _ = Menu.objects.get_or_create(
            name='角色管理',
            defaults={
                'code': 'sys:role:list',
                'path': '/system/role',
                'type': 'menu',
                'icon': 'UserFilled',
                'parent': system_dir,
                'order': 2,
            }
        )

        # 角色权限按钮
        Menu.objects.get_or_create(
            name='角色新增',
            defaults={
                'code': 'sys:role:add',
                'type': 'button',
                'parent': role_menu,
                'order': 1,
            }
        )
        Menu.objects.get_or_create(
            name='角色编辑',
            defaults={
                'code': 'sys:role:edit',
                'type': 'button',
                'parent': role_menu,
                'order': 2,
            }
        )
        Menu.objects.get_or_create(
            name='角色删除',
            defaults={
                'code': 'sys:role:delete',
                'type': 'button',
                'parent': role_menu,
                'order': 3,
            }
        )
        Menu.objects.get_or_create(
            name='角色权限',
            defaults={
                'code': 'sys:role:permission',
                'type': 'button',
                'parent': role_menu,
                'order': 4,
            }
        )

        # 用户管理
        user_menu, _ = Menu.objects.get_or_create(
            name='用户管理',
            defaults={
                'code': 'sys:user:list',
                'path': '/system/user',
                'type': 'menu',
                'icon': 'User',
                'parent': system_dir,
                'order': 3,
            }
        )

        # 用户权限按钮
        Menu.objects.get_or_create(
            name='用户新增',
            defaults={
                'code': 'sys:user:add',
                'type': 'button',
                'parent': user_menu,
                'order': 1,
            }
        )
        Menu.objects.get_or_create(
            name='用户编辑',
            defaults={
                'code': 'sys:user:edit',
                'type': 'button',
                'parent': user_menu,
                'order': 2,
            }
        )
        Menu.objects.get_or_create(
            name='用户删除',
            defaults={
                'code': 'sys:user:delete',
                'type': 'button',
                'parent': user_menu,
                'order': 3,
            }
        )
        Menu.objects.get_or_create(
            name='用户角色',
            defaults={
                'code': 'sys:user:role',
                'type': 'button',
                'parent': user_menu,
                'order': 4,
            }
        )
        Menu.objects.get_or_create(
            name='重置密码',
            defaults={
                'code': 'sys:user:reset-password',
                'type': 'button',
                'parent': user_menu,
                'order': 5,
            }
        )

        # 看板菜单
        board_menu, _ = Menu.objects.get_or_create(
            name='看板',
            defaults={
                'code': 'board:list',
                'path': '/board',
                'type': 'menu',
                'icon': 'Grid',
                'order': 1,
            }
        )

        # 成员管理
        member_menu, _ = Menu.objects.get_or_create(
            name='成员管理',
            defaults={
                'code': 'member:list',
                'path': '/members',
                'type': 'menu',
                'icon': 'User',
                'order': 2,
            }
        )

        # 标签管理
        Menu.objects.get_or_create(
            name='标签管理',
            defaults={
                'code': 'tag:list',
                'path': '/tags',
                'type': 'menu',
                'icon': 'Collection',
                'order': 3,
            }
        )

        # 统计报表
        Menu.objects.get_or_create(
            name='统计报表',
            defaults={
                'code': 'stats:list',
                'path': '/stats',
                'type': 'menu',
                'icon': 'DataLine',
                'order': 4,
            }
        )

        # 工具目录
        tools_dir, _ = Menu.objects.get_or_create(
            name='工具',
            defaults={
                'code': 'tools:manage',
                'path': '/tools',
                'type': 'directory',
                'icon': 'Tools',
                'order': 40,
            }
        )

        # 项目聊天
        Menu.objects.get_or_create(
            name='项目聊天',
            defaults={
                'code': 'chat:list',
                'path': '/chat',
                'type': 'menu',
                'icon': 'ChatLineRound',
                'parent': tools_dir,
                'order': 1,
            }
        )

        # AI助手
        Menu.objects.get_or_create(
            name='AI助手',
            defaults={
                'code': 'ai:chat',
                'path': '/ai-chat',
                'type': 'menu',
                'icon': 'ChatDotRound',
                'parent': tools_dir,
                'order': 2,
            }
        )

        # 消息
        Menu.objects.get_or_create(
            name='消息',
            defaults={
                'code': 'notification:list',
                'path': '/notifications',
                'type': 'menu',
                'icon': 'Bell',
                'parent': tools_dir,
                'order': 3,
            }
        )

        # 设置
        Menu.objects.get_or_create(
            name='设置',
            defaults={
                'code': 'settings:list',
                'path': '/settings',
                'type': 'menu',
                'icon': 'Setting',
                'parent': tools_dir,
                'order': 4,
            }
        )

        # 质量中心目录
        qa_dir, _ = Menu.objects.get_or_create(
            name='质量中心',
            defaults={
                'code': 'qa:manage',
                'path': '/qa',
                'type': 'directory',
                'icon': 'Monitor',
                'order': 50,
            }
        )

        # API测试
        Menu.objects.get_or_create(
            name='API测试',
            defaults={
                'code': 'qa:api:list',
                'path': '/qa/api-cases',
                'type': 'menu',
                'icon': 'Document',
                'parent': qa_dir,
                'order': 1,
            }
        )

        # UI测试
        Menu.objects.get_or_create(
            name='UI测试',
            defaults={
                'code': 'qa:ui:list',
                'path': '/qa/ui-cases',
                'type': 'menu',
                'icon': 'Monitor',
                'parent': qa_dir,
                'order': 2,
            }
        )

        # 测试结果
        Menu.objects.get_or_create(
            name='测试结果',
            defaults={
                'code': 'qa:result:list',
                'path': '/qa/test-results',
                'type': 'menu',
                'icon': 'DataLine',
                'parent': qa_dir,
                'order': 3,
            }
        )

        # 性能测试
        Menu.objects.get_or_create(
            name='性能测试',
            defaults={
                'code': 'qa:performance:list',
                'path': '/qa/performance',
                'type': 'menu',
                'icon': 'Lightning',
                'parent': qa_dir,
                'order': 4,
            }
        )

        # DevOps 内置测试平台
        Menu.objects.get_or_create(
            name='DevOps测试平台',
            defaults={
                'code': 'qa:devops:list',
                'path': '/qa/devops',
                'type': 'menu',
                'icon': 'Platform',
                'parent': qa_dir,
                'order': 5,
            }
        )

        self.stdout.write(f'  创建了 {Menu.objects.count()} 个菜单/权限')
        return Menu.objects.all()

    def create_roles(self, menus):
        """创建角色"""
        self.stdout.write('创建角色...')

        # 超级管理员
        admin_role, created = Role.objects.get_or_create(
            key='admin',
            defaults={
                'name': '超级管理员',
                'is_active': True,
            }
        )
        if created:
            admin_role.menus.set(menus)
            self.stdout.write('  创建角色: 超级管理员')

        # 普通用户
        user_role, created = Role.objects.get_or_create(
            key='user',
            defaults={
                'name': '普通用户',
                'is_active': True,
            }
        )
        if created:
            # 普通用户只有看板和成员管理的权限
            user_menus = menus.filter(code__in=['board:list', 'member:list'])
            user_role.menus.set(user_menus)
            self.stdout.write('  创建角色: 普通用户')

        # 测试人员
        tester_role, created = Role.objects.get_or_create(
            key='tester',
            defaults={
                'name': '测试人员',
                'is_active': True,
            }
        )
        if created:
            # 测试人员有质量中心权限
            tester_menus = menus.filter(
                code__in=['board:list', 'member:list', 'qa:manage', 'qa:api:list', 'qa:ui:list', 'qa:result:list']
            )
            tester_role.menus.set(tester_menus)
            self.stdout.write('  创建角色: 测试人员')

        return admin_role

    def assign_admin_role(self, admin_role):
        """为第一个超级用户分配管理员角色"""
        self.stdout.write('分配管理员角色...')

        # 获取第一个超级用户
        admin_user = User.objects.filter(is_superuser=True).first()
        if admin_user:
            profile, created = SystemUserProfile.objects.get_or_create(user=admin_user)
            if admin_role not in profile.roles.all():
                profile.roles.add(admin_role)
                self.stdout.write(f'  为用户 {admin_user.username} 分配了超级管理员角色')
        else:
            # 如果没有超级用户，为第一个用户分配
            first_user = User.objects.first()
            if first_user:
                profile, created = SystemUserProfile.objects.get_or_create(user=first_user)
                if admin_role not in profile.roles.all():
                    profile.roles.add(admin_role)
                    self.stdout.write(f'  为用户 {first_user.username} 分配了超级管理员角色')
