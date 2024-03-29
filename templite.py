import re

from codeBuilder import CodeBuilder
from exception import TempliteSyntaxError


class Templite(object):
    """模板类"""

    def __init__(self, text, *contexts):
        """把text转换成模板结构,context用于渲染的值字典"""
        self.context = {}
        for context in contexts:
            self.context.update(context)

        # 全局变量,eg. {{age}}
        self.all_vars = set()
        # 控制语句中自定义的变量
        self.loop_vars = set()

        code = CodeBuilder()

        code.add_line("def render_function(context,do_dots):")
        code.indent()
        vars_code = code.add_section()
        code.add_line("result = []")
        code.add_line("append_result = result.append")
        code.add_line("extend_result = result.extend")
        code.add_line("to_str = str")

        # 解析结果的缓冲列表
        buffered = []

        def flush_output():
            """清空缓存列表"""
            if len(buffered) == 1:
                code.add_line("append_result(%s)" % buffered[0])
            elif len(buffered) > 1:
                code.add_line("extend_result([%s])" % ", ".join(buffered))
            del buffered[:]

        # 控制语句 关键字堆栈
        ops_stack = []

        # 按照{{}}，{%%}，{##} 分割text
        tokens = re.split(r"(?s)({{.*?}}|{%.*?%}|{#.*?#})", text)

        for token in tokens:
            if token.startswith('{#'):
                # 该行是注释
                continue
            elif token.startswith('{{'):
                # 模板变量
                expr = self.__expr_code(token[2:-2].strip())
                # 添加到缓存中
                buffered.append("to_str(%s)" % expr)
            elif token.startswith('{%'):
                flush_output()
                words = token[2:-2].strip().split()
                if words[0] == 'if':
                    # 进一步判断
                    if len(words) != 2:
                        self._syntax_error("Don't understand if", token)
                    ops_stack.append('if')
                    code.add_line("if %s:" % self._expr_code(words[1]))
                    code.indent()
                elif words[0] == 'for':
                    # 处理循环结构
                    if len(words) != 4 or words[2] != 'in':
                        self._syntax_error("Don't understand for", token)
                    ops_stack.append('for')
                    self._variable(words[1], self.loop_vars)
                    code.add_line(
                        "for c_%s in %s:" % (
                            words[1],
                            self.__expr_code(words[3])
                        )
                    )
                    code.indent()
                elif words[0].startswith('end'):
                    # endif endfor ,弹出堆栈
                    if len(words) != 1:
                        self._syntax_error("Don't understand end", token)
                    end_what = words[0][3:]
                    if not ops_stack:
                        self._syntax_error("Too many ends", token)
                    start_what = ops_stack.pop()
                    if start_what != end_what:
                        self._syntax_error("Mismatched end tag", end_what)
                    code.dedent()
                else:
                    self._syntax_error("Don't understand tag", words[0])
            else:
                if token:
                    buffered.append(repr(token))

        if ops_stack:
            self._syntax_error("Unmatched action tag", ops_stack[-1])

        flush_output()

        for var_name in self.all_vars - self.loop_vars:
            vars_code.add_line("c_%s = context[%r]" % (var_name, var_name))

        code.add_line("return ''.join(result)")
        code.dedent()
        self._render_function = code.get_globals()['render_function']

    def __expr_code(self, expr):
        """生成python表达式,解析过滤器"""
        if "|" in expr:
            pipes = expr.split("|")
            code = self.__expr_code(pipes[0])
            for func in pipes[1:]:
                self._variable(func, self.all_vars)
                code = "c_%s(%s)" % (func, code)
        elif "." in expr:
            dots = expr.split(".")
            code = self.__expr_code(dots[0])
            args = ", ".join(repr(d) for d in dots[1:])
            code = "do_dots(%s,%s)" % (code, args)
        else:
            self._variable(expr, self.all_vars)
            code = "c_%s" % expr
        return code

    def _variable(self, name, vars_set):
        """解析变量名是否合法，不合法抛出模板语法异常"""
        if not re.match(r"[_a-zA-Z][_a-zA-Z0-9]*$", name):
            self._syntax_error("Not a valid name", name)
        vars_set.add(name)

    def _syntax_error(self, msg, thing):
        raise TempliteSyntaxError("%s: %r" % (msg, thing))

    def render(self, context=None):
        """通过context渲染模板"""
        render_context = dict(self.context)
        if context:
            render_context.update(context)
        return self._render_function(render_context, self._do_dots)

    def _do_dots(self, value, *dots):
        """执行.表达式"""
        for dot in dots:
            try:
                value = getattr(value, dot)
            except AttributeError:
                value = value[dot]
            if callable(value):
                value = value()
        return value
