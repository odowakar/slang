//------------------------------------------------------------------------------
// TimingControl.cpp
// Timing control creation and analysis
//
// File is under the MIT license; see LICENSE for details
//------------------------------------------------------------------------------
#include "slang/binding/TimingControl.h"

#include "slang/binding/Expression.h"
#include "slang/compilation/Compilation.h"
#include "slang/diagnostics/ExpressionsDiags.h"
#include "slang/diagnostics/StatementsDiags.h"
#include "slang/syntax/AllSyntax.h"
#include "slang/types/Type.h"

namespace slang {

const TimingControl& TimingControl::bind(const TimingControlSyntax& syntax,
                                         const BindContext& context) {
    auto& comp = context.getCompilation();
    if (context.flags.has(BindFlags::FunctionOrFinal)) {
        context.addDiag(diag::TimingInFuncNotAllowed, syntax.sourceRange());
        return badCtrl(comp, nullptr);
    }

    TimingControl* result;
    switch (syntax.kind) {
        case SyntaxKind::DelayControl:
            result = &DelayControl::fromSyntax(comp, syntax.as<DelaySyntax>(), context);
            break;
        case SyntaxKind::Delay3:
            result = &Delay3Control::fromSyntax(comp, syntax.as<Delay3Syntax>(), context);
            break;
        case SyntaxKind::EventControl:
            result =
                &SignalEventControl::fromSyntax(comp, syntax.as<EventControlSyntax>(), context);
            break;
        case SyntaxKind::EventControlWithExpression: {
            result = &EventListControl::fromSyntax(
                comp, *syntax.as<EventControlWithExpressionSyntax>().expr, context);
            break;
        }
        case SyntaxKind::ImplicitEventControl:
            result = &ImplicitEventControl::fromSyntax(
                comp, syntax.as<ImplicitEventControlSyntax>(), context);
            break;
        case SyntaxKind::RepeatedEventControl:
            result = &RepeatedEventControl::fromSyntax(
                comp, syntax.as<RepeatedEventControlSyntax>(), context);
            break;
        case SyntaxKind::OneStepDelay:
            result = comp.emplace<OneStepDelayControl>();
            break;
        case SyntaxKind::CycleDelay:
            result = &CycleDelayControl::fromSyntax(comp, syntax.as<DelaySyntax>(), context);
            break;
        default:
            THROW_UNREACHABLE;
    }

    result->syntax = &syntax;
    return *result;
}

TimingControl& TimingControl::badCtrl(Compilation& compilation, const TimingControl* ctrl) {
    return *compilation.emplace<InvalidTimingControl>(ctrl);
}

void InvalidTimingControl::serializeTo(ASTSerializer& serializer) const {
    if (child)
        serializer.write("child", *child);
}

TimingControl& DelayControl::fromSyntax(Compilation& compilation, const DelaySyntax& syntax,
                                        const BindContext& context) {
    auto& expr = Expression::bind(*syntax.delayValue, context);
    auto result = compilation.emplace<DelayControl>(expr);
    if (expr.bad())
        return badCtrl(compilation, result);

    if (!expr.type->isNumeric()) {
        context.addDiag(diag::DelayNotNumeric, expr.sourceRange) << *expr.type;
        return badCtrl(compilation, result);
    }

    return *result;
}

TimingControl& DelayControl::fromParams(Compilation& compilation,
                                        const ParameterValueAssignmentSyntax& exprs,
                                        const BindContext& context) {
    auto& items = exprs.parameters;
    if (items.size() != 1 || items[0]->kind != SyntaxKind::OrderedParamAssignment) {
        context.addDiag(diag::ExpectedNetDelay, exprs.sourceRange());
        return badCtrl(compilation, nullptr);
    }

    auto& expr = Expression::bind(*items[0]->as<OrderedParamAssignmentSyntax>().expr, context);
    auto result = compilation.emplace<DelayControl>(expr);
    if (expr.bad())
        return badCtrl(compilation, result);

    if (!expr.type->isNumeric()) {
        context.addDiag(diag::DelayNotNumeric, expr.sourceRange) << *expr.type;
        return badCtrl(compilation, result);
    }

    return *result;
}

void DelayControl::serializeTo(ASTSerializer& serializer) const {
    serializer.write("expr", expr);
}

TimingControl& Delay3Control::fromSyntax(Compilation& compilation, const Delay3Syntax& syntax,
                                         const BindContext& context) {
    auto& expr1 = Expression::bind(*syntax.delay1, context);

    const Expression* expr2 = nullptr;
    if (syntax.delay2)
        expr2 = &Expression::bind(*syntax.delay2, context);

    const Expression* expr3 = nullptr;
    if (syntax.delay3)
        expr3 = &Expression::bind(*syntax.delay3, context);

    auto result = compilation.emplace<Delay3Control>(expr1, expr2, expr3);
    if (expr1.bad() || (expr2 && expr2->bad()) || (expr3 && expr3->bad()))
        return badCtrl(compilation, result);

    auto checkType = [&](const Expression& expr) {
        if (!expr.type->isNumeric()) {
            context.addDiag(diag::DelayNotNumeric, expr.sourceRange) << *expr.type;
            return false;
        }
        return true;
    };

    if (!checkType(expr1) || (expr2 && !checkType(*expr2)) || (expr3 && !checkType(*expr3)))
        return badCtrl(compilation, result);

    return *result;
}

TimingControl& Delay3Control::fromParams(Compilation& compilation,
                                         const ParameterValueAssignmentSyntax& exprs,
                                         const BindContext& context) {
    auto& items = exprs.parameters;
    if (items.size() < 1 || items.size() > 3) {
        context.addDiag(diag::ExpectedNetDelay, exprs.sourceRange());
        return badCtrl(compilation, nullptr);
    }

    const Expression* delays[3] = { nullptr };
    for (size_t i = 0; i < items.size(); i++) {
        if (items[i]->kind != SyntaxKind::OrderedParamAssignment) {
            context.addDiag(diag::ExpectedNetDelay, items[i]->sourceRange());
            return badCtrl(compilation, nullptr);
        }

        delays[i] = &Expression::bind(*items[i]->as<OrderedParamAssignmentSyntax>().expr, context);

        if (!delays[i]->type->isNumeric()) {
            context.addDiag(diag::DelayNotNumeric, delays[i]->sourceRange) << *delays[i]->type;
            return badCtrl(compilation, nullptr);
        }
    }

    ASSERT(delays[0]);
    return *compilation.emplace<Delay3Control>(*delays[0], delays[1], delays[2]);
}

void Delay3Control::serializeTo(ASTSerializer& serializer) const {
    serializer.write("expr1", expr1);
    if (expr2)
        serializer.write("expr2", *expr2);
    if (expr3)
        serializer.write("expr3", *expr3);
}

TimingControl& SignalEventControl::fromSyntax(Compilation& compilation,
                                              const SignalEventExpressionSyntax& syntax,
                                              const BindContext& context) {
    auto edge = SemanticFacts::getEdgeKind(syntax.edge.kind);
    auto& expr = Expression::bind(*syntax.expr, context,
                                  BindFlags::EventExpression | BindFlags::AllowClockingBlock);

    const Expression* iffCond = nullptr;
    if (syntax.iffClause)
        iffCond = &Expression::bind(*syntax.iffClause->expr, context, BindFlags::EventExpression);

    return fromExpr(compilation, edge, expr, iffCond, context);
}

TimingControl& SignalEventControl::fromSyntax(Compilation& compilation,
                                              const EventControlSyntax& syntax,
                                              const BindContext& context) {
    auto& expr = Expression::bind(*syntax.eventName, context,
                                  BindFlags::EventExpression | BindFlags::AllowClockingBlock);
    return fromExpr(compilation, EdgeKind::None, expr, nullptr, context);
}

TimingControl& SignalEventControl::fromExpr(Compilation& compilation, EdgeKind edge,
                                            const Expression& expr, const Expression* iffCondition,
                                            const BindContext& context) {
    auto result = compilation.emplace<SignalEventControl>(edge, expr, iffCondition);
    if (expr.bad())
        return badCtrl(compilation, result);

    // Note: `expr` here can be a void-typed HierarchicalReferenceExpression if it's
    // referring to a clocking block.

    if (edge == EdgeKind::None) {
        if (expr.type->isAggregate() || expr.type->isCHandle()) {
            context.addDiag(diag::InvalidEventExpression, expr.sourceRange) << *expr.type;
            return badCtrl(compilation, result);
        }
    }
    else if (!expr.type->isIntegral()) {
        if (expr.type->isVoid())
            context.addDiag(diag::ClockingBlockEventEdge, expr.sourceRange);
        else
            context.addDiag(diag::ExprMustBeIntegral, expr.sourceRange) << *expr.type;
        return badCtrl(compilation, result);
    }

    if (iffCondition) {
        if (!context.requireBooleanConvertible(*iffCondition))
            return badCtrl(compilation, result);
    }

    // Warn if the expression is constant, since it'll never change to trigger off.
    if (context.tryEval(expr))
        context.addDiag(diag::EventExpressionConstant, expr.sourceRange);

    return *result;
}

void SignalEventControl::serializeTo(ASTSerializer& serializer) const {
    serializer.write("expr", expr);
    serializer.write("edge", toString(edge));
}

static void collectEvents(const BindContext& context, const EventExpressionSyntax& expr,
                          SmallVector<TimingControl*>& results) {
    switch (expr.kind) {
        case SyntaxKind::ParenthesizedEventExpression:
            collectEvents(context, *expr.as<ParenthesizedEventExpressionSyntax>().expr, results);
            break;
        case SyntaxKind::SignalEventExpression:
            results.append(&SignalEventControl::fromSyntax(
                context.getCompilation(), expr.as<SignalEventExpressionSyntax>(), context));
            break;
        case SyntaxKind::BinaryEventExpression: {
            auto& bin = expr.as<BinaryEventExpressionSyntax>();
            collectEvents(context, *bin.left, results);
            collectEvents(context, *bin.right, results);
            break;
        }
        default:
            THROW_UNREACHABLE;
    }
}

TimingControl& EventListControl::fromSyntax(Compilation& compilation,
                                            const EventExpressionSyntax& syntax,
                                            const BindContext& context) {
    SmallVectorSized<TimingControl*, 4> events;
    collectEvents(context, syntax, events);

    if (events.size() == 1)
        return *events[0];

    auto result = compilation.emplace<EventListControl>(events.ccopy(compilation));
    for (auto ev : events) {
        if (ev->bad())
            return badCtrl(compilation, result);
    }

    return *result;
}

void EventListControl::serializeTo(ASTSerializer& serializer) const {
    serializer.startArray("events");
    for (auto const event : events) {
        serializer.serialize(*event);
    }
    serializer.endArray();
}

TimingControl& ImplicitEventControl::fromSyntax(Compilation& compilation,
                                                const ImplicitEventControlSyntax&,
                                                const BindContext&) {
    // Nothing to do here except return the object.
    return *compilation.emplace<ImplicitEventControl>();
}

TimingControl& RepeatedEventControl::fromSyntax(Compilation& compilation,
                                                const RepeatedEventControlSyntax& syntax,
                                                const BindContext& context) {
    if (!syntax.eventControl) {
        context.addDiag(diag::RepeatControlNotEvent, syntax.sourceRange());
        return badCtrl(compilation, nullptr);
    }

    auto& expr = Expression::bind(*syntax.expr, context);
    auto& event = TimingControl::bind(*syntax.eventControl, context);
    auto result = compilation.emplace<RepeatedEventControl>(expr, event);
    if (expr.bad())
        return badCtrl(compilation, result);

    if (!expr.type->isNumeric()) {
        context.addDiag(diag::RepeatNotNumeric, expr.sourceRange) << *expr.type;
        return badCtrl(compilation, result);
    }

    if (event.kind != TimingControlKind::SignalEvent &&
        event.kind != TimingControlKind::EventList &&
        event.kind != TimingControlKind::ImplicitEvent) {
        context.addDiag(diag::RepeatControlNotEvent, syntax.eventControl->sourceRange());
        return badCtrl(compilation, result);
    }

    return *result;
}

void RepeatedEventControl::serializeTo(ASTSerializer& serializer) const {
    serializer.write("expr", expr);
    serializer.write("event", event);
}

TimingControl& CycleDelayControl::fromSyntax(Compilation& compilation, const DelaySyntax& syntax,
                                             const BindContext& context) {
    auto& expr = Expression::bind(*syntax.delayValue, context);
    auto result = compilation.emplace<CycleDelayControl>(expr);
    if (expr.bad())
        return badCtrl(compilation, result);

    if (!expr.type->isIntegral()) {
        context.addDiag(diag::ExprMustBeIntegral, expr.sourceRange) << *expr.type;
        return badCtrl(compilation, result);
    }

    if (!compilation.getDefaultClocking(*context.scope))
        context.addDiag(diag::NoDefaultClocking, syntax.sourceRange());

    return *result;
}

void CycleDelayControl::serializeTo(ASTSerializer& serializer) const {
    serializer.write("expr", expr);
}

} // namespace slang
