# Repair request (attempt 2)

The candidate from attempt 1 failed independent checks. Fix the
package in package/ so every check in PLAN.md passes. Do not work around a check;
make the App behave as required.
Repairs left after this one: 1.

## Failed checks

### seal.ui_build

the UI did not compile: type errors in the screen (TypeScript strict, kit types):
main.tsx(96,61): error TS2322: Type 'Dispatch<SetStateAction<string>>' is not assignable to type 'ChangeEventHandler<HTMLInputElement, HTMLInputElement>'.
  Types of parameters 'value' and 'event' are incompatible.
    Type 'ChangeEvent<HTMLInputElement, HTMLInputElement>' is not assignable to type 'SetStateAction<string>'.
main.tsx(97,55): error TS2322: Type 'Dispatch<SetStateAction<string>>' is not assignable to type 'ChangeEventHandler<HTMLInputElement, HTMLInputElement>'.
  Types of parameters 'value' and 'event' are incompatible.
    Type 'ChangeEvent<HTMLInputElement, HTMLInputElement>' is not assignable to type 'SetStateAction<string>'.
main.tsx(98,60): error TS2322: Type 'Dispatch<SetStateAction<string>>' is not assignable to type 'ChangeEventHandler<HTMLInputElement, HTMLInputElement>'.
  Types of parameters 'value' and 'event' are incompatible.
    Type 'ChangeEvent<HTMLInputElement, HTMLInputEl

```json
{
  "log_tail": "ui build failed: type errors in the screen (TypeScript strict, kit types):\nmain.tsx(96,61): error TS2322: Type 'Dispatch<SetStateAction<string>>' is not assignable to type 'ChangeEventHandler<HTMLInputElement, HTMLInputElement>'.\n  Types of parameters 'value' and 'event' are incompatible.\n    Type 'ChangeEvent<HTMLInputElement, HTMLInputElement>' is not assignable to type 'SetStateAction<string>'.\nmain.tsx(97,55): error TS2322: Type 'Dispatch<SetStateAction<string>>' is not assignable to type 'ChangeEventHandler<HTMLInputElement, HTMLInputElement>'.\n  Types of parameters 'value' and 'event' are incompatible.\n    Type 'ChangeEvent<HTMLInputElement, HTMLInputElement>' is not assignable to type 'SetStateAction<string>'.\nmain.tsx(98,60): error TS2322: Type 'Dispatch<SetStateAction<string>>' is not assignable to type 'ChangeEventHandler<HTMLInputElement, HTMLInputElement>'.\n  Types of parameters 'value' and 'event' are incompatible.\n    Type 'ChangeEvent<HTMLInputElement, HTMLInputElement>' is not assignable to type 'SetStateAction<string>'.\nmain.tsx(99,46): error TS2322: Type 'Dispatch<SetStateAction<string>>' is not assignable to type 'ChangeEventHandler<HTMLInputElement, HTMLInputElement>'.\n  Types of parameters 'value' and 'event' are incompatible.\n    Type 'ChangeEvent<HTMLInputElement, HTMLInputElement>' is not assignable to type 'SetStateAction<string>'.\nmain.tsx(100,52): error TS2322: Type 'Dispatch<SetStateAction<string>>' is not assignable to type 'ChangeEventHandler<HTMLTextAreaElement, HTMLTextAreaElement>'.\n  Types of parameters 'value' and 'event' are incompatible.\n    Type 'ChangeEvent<HTMLTextAreaElement, HTMLTextAreaElement>' is not assignable to type 'SetStateAction<string>'.\nmain.tsx(159,61): error TS2322: Type 'Dispatch<SetStateAction<string>>' is not assignable to type 'ChangeEventHandler<HTMLInputElement, HTMLInputElement>'.\n  Types of parameters 'value' and 'event' are incompatible.\n    Type 'ChangeEvent<HTMLInputElement, HTMLInputElement>' is not assignable to type 'SetStateAction<string>'.\nmain.tsx(164,17): error TS2322: Type 'Dispatch<SetStateAction<string>>' is not assignable to type 'ChangeEventHandler<HTMLSelectElement, HTMLSelectElement>'.\n  Types of parameters 'value' and 'event' are incompatible.\n"
}
```

## Not run because of the failures above

- handlers.not_run: not run: the seal stage did not pass
- behavior.not_run: not run: the seal stage did not pass
- ui.not_run: not run: the seal stage did not pass
