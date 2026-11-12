PROJECTS := $(patsubst %/Makefile,%,$(wildcard */Makefile))
SELECTED := $(filter $(PROJECTS),$(MAKECMDGOALS))

ifeq ($(words $(SELECTED)),0)
ifeq ($(strip $(MAKECMDGOALS)),)
.DEFAULT_GOAL := help
else ifneq ($(strip $(filter-out help list,$(MAKECMDGOALS))),)
$(error Select one of: $(PROJECTS))
endif
.PHONY: help list
help list:
	@printf '%s\n' 'Projects: $(PROJECTS)' 'Use make <project> help for commands.'
else ifneq ($(words $(SELECTED)),1)
$(error Select exactly one project: $(PROJECTS))
else
PROJECT := $(firstword $(SELECTED))
SUBGOALS := $(filter-out $(PROJECT),$(MAKECMDGOALS))
.PHONY: $(PROJECT) $(SUBGOALS)
$(PROJECT):
	+$(MAKE) -C $(PROJECT) $(SUBGOALS)
$(SUBGOALS): $(PROJECT)
	@:
endif
